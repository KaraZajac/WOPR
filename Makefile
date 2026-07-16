# WOPR — pipeline + verification gate. See README.md and docs/.

.PHONY: pull build verify test score status export site site-dev install-hooks help

help:                ## list targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

pull:                ## download UCDP sources into sources/
	@python3 -m wopr pull

build:               ## build data/ tables + registries from sources/
	@python3 -m wopr build

verify:              ## validation gate: data + journal checks, then unit tests
	@python3 -m wopr verify
	@python3 -m unittest discover -s tests -q

test:                ## unit tests only
	@python3 -m unittest discover -s tests -q

score:               ## scorecard: Brier/log/calibration, you vs the prior
	@python3 -m wopr score

status:              ## open questions and data coverage
	@python3 -m wopr status

export:              ## write data/site/*.json for the Astro site
	@python3 -m wopr.pipeline.site_export

site: export         ## build the static site (site/dist)
	@cd site && npm run build

site-dev: export     ## run the site dev server
	@cd site && npm run dev

install-hooks:       ## enable the git pre-commit gate for this clone
	@chmod +x .githooks/pre-commit
	@git config core.hooksPath .githooks
	@echo "✓ pre-commit gate installed (core.hooksPath=.githooks). Bypass once with: git commit --no-verify"
