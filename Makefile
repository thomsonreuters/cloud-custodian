
install:
	python3 -m venv .
	. bin/activate && pip install -r requirements-dev.txt
	. bin/activate && pip install -e .
	. bin/activate && pip install -r tools/c7n_mailer/requirements.txt
	. bin/activate && pip install -r tools/c7n_azure/requirements.txt
	. bin/activate && pip install -r tools/c7n_gcp/requirements.txt
	. bin/activate && pip install -r tools/c7n_kube/requirements.txt

test:
	./bin/tox -e py27

test3:
	./bin/tox -e py37

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

docker-image:
	docker build -t docker-c7n-image .

docker-interactive:
	docker run -it --rm \
	-e AWS_ACCESS_KEY_ID=`aws --profile default configure get aws_access_key_id` \
	-e AWS_SECRET_ACCESS_KEY=`aws --profile default configure get aws_secret_access_key` \
	-e AWS_SESSION_TOKEN=`aws --profile default configure get aws_session_token` \
	docker-c7n-image
