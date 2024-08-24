from policyengine_core.data import Dataset
import pandas as pd
from policyengine_us_data.utils import (
    pe_to_soi,
    get_soi,
    build_loss_matrix,
    fmt,
)
import numpy as np
from typing import Type
from policyengine_us_data.data_storage import STORAGE_FOLDER
from policyengine_us_data.datasets.cps import ExtendedCPS_2024
import torch


def build_loss_matrix(dataset: type, time_period):
    loss_matrix = pd.DataFrame()
    df = pe_to_soi(dataset, time_period)
    agi = df["adjusted_gross_income"].values
    filer = df["is_tax_filer"].values
    soi_subset = get_soi(time_period)
    targets_array = []
    agi_level_targeted_variables = [
        "adjusted_gross_income",
        "count",
        "employment_income",
        "business_net_profits",
        "capital_gains_gross",
        "ordinary_dividends",
        "partnership_and_s_corp_income",
        "qualified_dividends",
        "taxable_interest_income",
        "total_pension_income",
        "total_social_security",
    ]
    aggregate_level_targeted_variables = [
        "business_net_losses",
        "capital_gains_distributions",
        "capital_gains_losses",
        "estate_income",
        "estate_losses",
        "exempt_interest",
        "ira_distributions",
        "partnership_and_s_corp_losses",
        "rent_and_royalty_net_income",
        "rent_and_royalty_net_losses",
        "taxable_pension_income",
        "taxable_social_security",
        "unemployment_compensation",
    ]
    aggregate_level_targeted_variables = [
        variable
        for variable in aggregate_level_targeted_variables
        if variable in df.columns
    ]
    soi_subset = soi_subset[
        soi_subset.Variable.isin(agi_level_targeted_variables)
        & (
            (soi_subset["AGI lower bound"] != -np.inf)
            | (soi_subset["AGI upper bound"] != np.inf)
        )
        | (
            soi_subset.Variable.isin(aggregate_level_targeted_variables)
            & (soi_subset["AGI lower bound"] == -np.inf)
            & (soi_subset["AGI upper bound"] == np.inf)
        )
    ]
    for _, row in soi_subset.iterrows():
        if row["Taxable only"]:
            continue  # exclude "taxable returns" statistics

        mask = (
            (agi >= row["AGI lower bound"])
            * (agi < row["AGI upper bound"])
            * filer
        ) > 0

        if row["Filing status"] == "Single":
            mask *= df["filing_status"].values == "SINGLE"
        elif row["Filing status"] == "Married Filing Jointly/Surviving Spouse":
            mask *= df["filing_status"].values == "JOINT"
        elif row["Filing status"] == "Head of Household":
            mask *= df["filing_status"].values == "HEAD_OF_HOUSEHOLD"
        elif row["Filing status"] == "Married Filing Separately":
            mask *= df["filing_status"].values == "SEPARATE"

        values = df[row["Variable"]].values

        if row["Count"]:
            values = (values > 0).astype(float)

        agi_range_label = (
            f"{fmt(row['AGI lower bound'])}-{fmt(row['AGI upper bound'])}"
        )
        taxable_label = (
            "taxable" if row["Taxable only"] else "all" + " returns"
        )
        filing_status_label = row["Filing status"]

        variable_label = row["Variable"].replace("_", " ")

        if row["Count"] and not row["Variable"] == "count":
            label = (
                f"{variable_label}/count/AGI in "
                f"{agi_range_label}/{taxable_label}/{filing_status_label}"
            )
        elif row["Variable"] == "count":
            label = (
                f"{variable_label}/count/AGI in "
                f"{agi_range_label}/{taxable_label}/{filing_status_label}"
            )
        else:
            label = (
                f"{variable_label}/total/AGI in "
                f"{agi_range_label}/{taxable_label}/{filing_status_label}"
            )

        if label not in loss_matrix.columns:
            loss_matrix[label] = mask * values
            targets_array.append(row["Value"])

    # Convert tax-unit level df to household-level df

    from policyengine_us import Microsimulation

    sim = Microsimulation(dataset=dataset)
    hh_id = sim.calculate("household_id", map_to="person")
    tax_unit_hh_id = sim.map_result(
        hh_id, "person", "tax_unit", how="value_from_first_person"
    )

    loss_matrix = loss_matrix.groupby(tax_unit_hh_id).sum()

    return loss_matrix.values, np.array(targets_array)


def reweight(
    original_weights,
    loss_matrix,
    targets_array,
):
    loss_matrix = torch.tensor(loss_matrix, dtype=torch.float32)
    targets_array = torch.tensor(targets_array, dtype=torch.float32)

    # TODO: replace this with a call to the python reweight.py package.
    def loss(weights):
        estimate = weights @ loss_matrix
        rel_error = ((estimate - targets_array) / targets_array) ** 2
        return rel_error.mean()

    weights = torch.tensor(
        np.log(original_weights), requires_grad=True, dtype=torch.float32
    )
    optimizer = torch.optim.Adam([weights], lr=1e-2)
    from tqdm import trange

    iterator = trange(1_000)
    for i in iterator:
        optimizer.zero_grad()
        l = loss(torch.exp(weights))
        l.backward()
        iterator.set_postfix({"loss": l.item()})
        optimizer.step()

    return torch.exp(weights).detach().numpy()


class EnhancedCPS(Dataset):
    data_format = Dataset.FLAT_FILE
    input_dataset: Type[Dataset]
    start_year: int
    end_year: int

    def generate(self):
        df = self.input_dataset(require=True).load()
        from policyengine_us import Microsimulation

        sim = Microsimulation(dataset=self.input_dataset)
        original_weights = sim.calculate("household_weight")
        original_weights = original_weights.values + np.random.normal(
            10, 1, len(original_weights)
        )
        for year in range(self.start_year, self.end_year + 1):
            print(f"Enhancing CPS for {year}")
            loss_matrix, targets_array = build_loss_matrix(
                self.input_dataset, year
            )
            optimised_weights = reweight(
                original_weights, loss_matrix, targets_array
            )
            df[f"household_weight__{year}"] = sim.map_result(
                optimised_weights, "household", "person"
            )

        self.save_dataset(df)


class EnhancedCPS_2024(EnhancedCPS):
    input_dataset = ExtendedCPS_2024
    start_year = 2024
    end_year = 2024
    name = "enhanced_cps_2024"
    label = "Enhanced CPS 2024"
    file_path = STORAGE_FOLDER / "enhanced_cps_2024.csv"


if __name__ == "__main__":
    EnhancedCPS_2024().generate()
