# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Python template

[![codecov](https://codecov.io/gh/lidofinance/python-base-template/branch/master/graph/badge.svg)](https://codecov.io/gh/lidofinance/lido-python-sdk)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Super-Linter](https://github.com/lidofinance/python-base-template/workflows/Lint%20Code%20Base/badge.svg)](https://github.com/marketplace/actions/super-linter)

## General

This is pure python 3 template for new projects and bots on GitHub.

### HOW TO USE THIS TEMPLATE

> **DO NOT FORK** this is meant to be used from **[Use this template](https://github.com/lidofinance/python-base-template/generate)** feature.

1. Click on **[Use this template](https://github.com/lidofinance/python-base-template/generate)**
2. Give a name to your project  
   (e.g. `my_awesome_project` recommendation is to use all lowercase and underscores separation for repository names.)
3. Rename `myproject` to `{your_project_name}`
4. If you want [codecov](https://about.codecov.io/sign-up/) Reports
   on the new repository `settings->secrets` add your `CODECOV_TOKEN` (get the tokens on respective websites)
5. Then clone your new project and happy coding!

### Secrets

List of secrets that you should add to secrets

* TARGET_REPO - Repository with our infra (lidofinance/infra-mainnet). This var need to run workflows from target repository.
* APP_ID and APP_PRIVATE_KEY - are ID and key to application that calls workflows in another application.

## What is included on this template?

- 🐋 A simple [Dockerfile](Dockerfile) to build a container image for your project.  
- 🧪 Testing structure using [pytest](https://docs.pytest.org/en/latest/).
- 🔄 Continuous integration using [GitHub Actions](.github/workflows/) with jobs to lint, tests.
- ✅ Code linting using [pylint](https://pylint.org/), [isort](https://pycqa.github.io/isort/), [mypy](https://mypy.readthedocs.io/en/stable/) and [bandit](https://bandit.readthedocs.io/en/latest/) via [Lido generic workflow](https://github.com/lidofinance/linters)
- 🌊 Tracking and logging via [Prometheus](https://prometheus.io/).
- 📊 Code coverage reports using [codecov](https://about.codecov.io/sign-up/)
- 🧙‍ To sort dependencies [isort](https://pycqa.github.io/isort/).
- 🛑 Check everything before push [pre-commit](https://pre-commit.com/).
- 🦸 Lint everything with [super-linter](https://github.com/github/super-linter).

<!--  DELETE THE LINES ABOVE THIS AND WRITE YOUR PROJECT README BELOW -->

---
# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> My Project

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/lidofinance/python-base-template/actions/workflows/main.yml/tests.svg)](https://github.com/lidofinance/python-base-template/actions/workflows/main.yml)

Myproject is a base template for all python project with preinstalled packages that are common for Lido's codebase.

## How to install

1. `poetry install` - to install dep
2. `pre-commit install` - to install pre-commit hooks

## Usage

```py
from myproject import BaseClass
from myproject import base_function

BaseClass().base_method()
base_function()
```

```bash
$ python -m myproject

Hello world!
```
