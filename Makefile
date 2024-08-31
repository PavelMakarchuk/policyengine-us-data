all: data test

format:
	black . -l 79

test:
	pytest policyengine_us_data/tests

install:
	pip install -e .[dev]

download:
	python policyengine_us_data/data_storage/download_public_prerequisites.py
	python policyengine_us_data/data_storage/download_private_prerequisites.py

upload:
	python policyengine_us_data/data_storage/upload_completed_datasets.py

docker:
	docker buildx build --platform linux/amd64 . -t policyengine-us-data:latest

documentation:
	streamlit run docs/Home.py

data:
	python policyengine_us_data/datasets/cps/enhanced_cps.py

clean:
	rm policyengine_us_data/data_storage/puf_2015.csv
	rm policyengine_us_data/data_storage/demographics_2015.csv
build:
	python setup.py sdist bdist_wheel