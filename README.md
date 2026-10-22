# Purpose
These deployments are intended for testing out a complete FL-Net Network on one single machine.
- If you're a developer and want to end-to-end test before contributing any bigger code changes
- If you're interested in FL-Net and want to try it out with dummy data and full admin access

# Quickstart
If you just want to try it out with default settings:
```bash
python3 init_test_bundle.py # just needs python3, no non stdlib packages required
sh start_test_bundle.sh
```
Then open the Platform UI at http://localhost:8250 and the two clients at http://localhost:8251 and http://127.0.0.1:8252 (Do NOT use localhost for the second client or the authentication for that client won't work). The Platform has the admin user `admin` with password `test`, the clients have the user `test` with password `test`. All Tools are owned by the admin user.
Wait a few minutes until the example Tool, the Schemas and the cohorts of the clients appear.

If you want to try out the federated learning, you can use the suggested [example FL workflow](#example-fl-workflow).

# Intended developer Flow 
## Prerequisites
- Docker and Docker Compose, Python 3 and curl on your machine.
- [Git LFS](https://git-lfs.com/) installed (`git lfs install`) before cloning: the SapBERT model `data/sapbert/sapbert.onnx` is stored with Git LFS. If you cloned without it, run `git lfs pull` in this directory afterwards, otherwise the file is only a small pointer file.
- Build the docker image for each service you changed. The building depends on the repo, helepr scripts may be available.
**Important: You can give these images any name, but end their name with `:testingtag` or `:tmptag`, e.g. `locallearning:testingtag`. The `start_test_bundle.sh` script tries to pull any image without the these suffixes.**

## 1. Prepare the platform and clients
You need to prepare the docker images of the services you changed and want to test.
Simply:
1. Build the images using the `dev_scripts/build_local_docker_image.sh` script in the repo of the service you changed. This will build the image and tag it with correctly with `:testingtag`.
2. Edit the `overrides/images_used.env` file in this directory to point to the images you built. 
There should be a commented out line for each image if built locally. Uncomment that line and comment out the line pointing to the `:staging` image.

Example:
```
#ORCH_API_IMAGE=ghcr.io/fedlearnnet/orchestration-api/orch-api:staging
ORCH_API_IMAGE=orch-api:testingtag
```

3. Generate the deployments (`platforms/test`, `clients/c1`, `clients/c2`) with the flnet CLI:
`python3 init_test_bundle.py`
It installs the `staging` release of the CLI into `bin/` (use `FLNET_BIN=/path/to/flnet` for e.g. a local CLI
build), runs `flnet platform init` and `flnet client init` and applies the testing changes from `overrides/`.
Only needed once, again after the CLI changed. If deployments already exist it deletes them including all
their data (docker volumes) after you confirmed.

## 2. Start the platform and clients
`sh start_test_bundle.sh`
Further information about the deployments of the testing bundle:
```
Platform + client urls:
Platform: http://localhost:8250
Client 1: http://localhost:8251
Client 2: http://127.0.0.1:8252

Platform + client credentials:
Username: admin
Password: test

Username: test
Password: test

All Tools are owned by the admin user
```
*Client 2 runs on `127.0.0.1` instead of `localhost` on purpose: browsers share cookies across ports of the same host, so two clients on `localhost` would overwrite each other's login session (backend-for-frontend session and Keycloak SSO cookies) and log each other out. Don't open client 2 via `localhost:8252`.*

## 3. Data on the platform and clients (automatic)
### Platform
- The Platform's datamodeler imports ontologies, datatypes and schemas, including the US-130 schema.
- The Platform imports and builds the US-130 NN Tool.

### Clients
- Each client creates the cohort "US 130 Schema" (owned by the `test` user), imports the connector `import_data_handling/us-130_connector.json` and runs it with its data file (`clinic_001.csv` on client 1, `clinic_002.csv` on client 2, set in `CLIENTS` of `init_test_bundle.py`).
Each client will hold ~700 patients. Each cohort will have automatic training access for ALL Tools.

The clients wait 1 minute after their start before creating the cohort (`flnet.auto-subscribe.delay=PT1M` in
`overrides/client.override.yml`), so the Platform's datamodeler has finished importing the schemas; Sometimes it may create the cohort based on a half-imported schema, which will fail the auto import. The easiest is to then delete the cohort in the frontend and restart the relevant clients local learning api, that will retrigger the import.

*The whole initial setup might take some time (5-10 minutes), you can watch the logs of the `global-learning-api` for the Tool building process and the `local-learning-api` for the data import process. After this process is completed you can restart also with updated service images and the data will be immediately available due to the persistent volumes used.*

## 4. Iterative development
Generally, use this to test whatever you are developing or want to test. The flow should be the same as if this was a production deployment, so what you do here depends on your changes and what you want to test/try out.

If you updated the image of a service, you can restart the testing bundle with `sh start_test_bundle.sh` again. The data and tools will be preserved, so you can immediately test your changes.
Furthermore, any compose command works as usual from within a deployment directory (`platforms/test`, `clients/c1`, `clients/c2`), e.g. in `clients/c1`:

`docker compose up -d`, `docker compose logs -f local-learning-api`, `docker compose down -v`

The services are defined in `docker-compose.base.yml`, the unmodified output of the flnet CLI. The `docker-compose.yml` next to it (copied from `overrides/*.compose.yml`) only includes that file merged with the testing-bundle override `overrides/*.override.yml`, together with the deployment's `.env` and the shared `overrides/images_used.env`, so the images set there are used without passing `--env-file`.

**Don't change anything in `platforms/` or `clients/`:** they are generated by `init_test_bundle.py` and not committed. Put testing changes into `overrides/` (compose overrides, wrapper templates, `images_used.env`, Keycloak users in `realm-users/`) or the CLI flags into `init_test_bundle.py`, then run it again.

*The OIDC of the local learning API might spam quite a bit of failures while the global Keycloak is not yet ready, but it should work after a few seconds.*

### Example FL workflow
The following FL project is used for testing and should work. If your changes break this, please do not merge them.
1. Go to the Platform UI (localhost:8250) and run a query. You can use `Hospital Readmission exists`.
*Sometimes it takes a while to load the available variables, if there's nothing to select from, reopen the query page.*
2. Create a FL project based on that query (Training tab):
- For the dataset get all variables (there's a button for that), make sure to pivot to wide format joining on patient_id, use keep first as duplicate handling. *Make sure to click the save button.*
- Add the US130-Hospital Readmission Federated NN Tool and connect the `csv input-data` into that Tool. Make sure to click on the gear icon of the tool to save the hyperparameters (the default ones work).
*Make sure to click the save button!*

# Disclaimer
This testing bundle uses third-party data and models only for testing purposes. All credit goes to their original authors. The bundle is not affiliated with or endorsed by them.

## Dataset: Diabetes 130-US Hospitals for Years 1999-2008
The test data used to fill the clients (see `import_data_handling/`) comes from the *Diabetes 130-US Hospitals for Years 1999-2008* dataset from the UCI Machine Learning Repository, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Dataset: https://archive.ics.uci.edu/dataset/296/diabetes+130-us+hospitals+for+years+1999-2008
- Clore, J., Cios, K., DeShazo, J., & Strack, B. (2014). *Diabetes 130-US Hospitals for Years 1999-2008* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5230J
- Strack, B., DeShazo, J. P., Gennings, C., Olmo, J. L., Ventura, S., Cios, K. J., & Clore, J. N. (2014). Impact of HbA1c Measurement on Hospital Readmission Rates: Analysis of 70,000 Clinical Database Patient Records. *BioMed Research International*, 2014, 781670. https://doi.org/10.1155/2014/781670

## Embedding model: SapBERT
The embedding model mounted into the platform (`data/sapbert/`) is an ONNX export of SapBERT by the Cambridge Language Technology Lab.
- Repository: https://github.com/cambridgeltl/sapbert
- Liu, F., Shareghi, E., Meng, Z., Basaldella, M., & Collier, N. (2021). Self-Alignment Pretraining for Biomedical Entity Representations. In *Proceedings of the 2021 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies* (pp. 4228–4238). https://aclanthology.org/2021.naacl-main.334
