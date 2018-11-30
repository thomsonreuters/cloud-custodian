
install:
	python3.6 -m virtualenv --python python3.6 .
	. bin/activate && pip install -r requirements-dev.txt
	. bin/activate && pip install -e .
	. bin/activate && pip install -r tools/c7n_mailer/requirements.txt
	. bin/activate && pip install -r tools/c7n_azure/requirements.txt
	. bin/activate && pip install -r tools/c7n_gcp/requirements.txt
	. bin/activate && pip install -r tools/c7n_kube/requirements.txt

coverage:
	rm -Rf .coverage
	AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=foo AWS_SECRET_ACCESS_KEY=bar C7N_VALIDATE=true nosetests -s -v --with-coverage --cover-html --cover-package=c7n --cover-html-dir=coverage --processes=-1 --cover-inclusive tests  --process-timeout=64

test:
	./bin/tox -e py27

test3:
	./bin/tox -e py36

nose-tests:
	AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=foo AWS_SECRET_ACCESS_KEY=bar C7N_VALIDATE=true nosetests -s -v --processes=-1 --process-timeout=300 tests


azure-tests:

	C7N_VALIDATE=true AZURE_ACCESS_TOKEN=fake_token AZURE_SUBSCRIPTION_ID=ea42f556-5106-4743-99b0-c129bfa71a47 ./bin/py.test --tb=native tools/c7n_azure

ttest:
	AWS_DEFAULT_REGION=us-east-1 nosetests -s --with-timer --process-timeout=300 tests

depcache:
	mkdir -p deps
	python -m virtualenv --python python2.7 dep-download
	dep-download/bin/pip install -d deps -r requirements.txt
	tar cvf custodian-deps.tgz deps
	rm -Rf dep-download
	rm -Rf deps

ftest:
	C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 ./bin/py.test -m functional tests

sphinx:
	make -f docs/Makefile.sphinx clean && \
	make -f docs/Makefile.sphinx html

ghpages:
	-git checkout gh-pages && \
	mv docs/build/html new-docs && \
	rm -rf docs && \
	mv new-docs docs && \
	git add -u && \
	git add -A && \
	git commit -m "Updated generated Sphinx documentation"

lint:
	flake8 c7n tools tests

clean:
	rm -rf .tox .Python bin include lib pip-selfcheck.json

docker-test-image:
	docker build -f Dockerfile.test -t docker-c7n-test-image .

docker-test: docker-test-image
	docker run -it --rm \
	docker-c7n-test-image

docker-interactive-image:
	docker build -f Dockerfile.interactive -t docker-c7n-image .

docker-interactive: docker-interactive-image
	docker run -it --rm \
	-e AWS_ACCESS_KEY_ID=`aws configure get aws_access_key_id` \
	-e AWS_SECRET_ACCESS_KEY=`aws configure get aws_secret_access_key` \
	-e AWS_SESSION_TOKEN=`aws configure get aws_session_token` \
	docker-c7n-image
