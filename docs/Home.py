import streamlit as st

st.title("PolicyEngine-US-Data")

st.write(
    """PolicyEngine-US-Data is a package to create representative microdata for the US, designed for input in the PolicyEngine tax-benefit microsimulation model."""
)

st.subheader("What does this repo do?")

st.write(
    """Principally, this package creates a (partly synthetic) dataset of households (with incomes, demographics and more) that describes the U.S. household sector. This dataset synthesises multiple sources of data (the Current Population Survey, the IRS Public Use File, and administrative statistics) to improve upon the accuracy of **any** of them."""
)

st.subheader("What does this dataset look like?")

st.write("The below table shows an extract of the person records in one household in the dataset.")

import pandas as pd
from policyengine_us_data.datasets import EnhancedCPS_2024

df = pd.read_csv(EnhancedCPS_2024().file_path)

household_id = df[
    df.filing_status__2024 == "JOINT"
].person_household_id__2024.values[0]
people_in_household = df[df.person_household_id__2024 == household_id]

st.dataframe(people_in_household.T, use_container_width=True)
