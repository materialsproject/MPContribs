BASE := $(shell /bin/pwd)

#############
#  SAM vars	#
#############

# Name of Docker Network to connect to
# Helpful when you're running Amazon DynamoDB local etc.
NETWORK = docker_internet
BUILDDIR = ${HOME}/.aws-sam
REGION = us-east-1

target:
	$(info ${HELP_MESSAGE})
	@exit 0

clean: ##=> Deletes current build environment and latest build
	$(info [*] Who needs all that anyway? Destroying environment....)
	rm -rf ${BUILDDIR}

all: clean build

build: ##=> Same as package except that we don't create a ZIP
	sam build --use-container -b ${BUILDDIR} --docker-network ${NETWORK} --parallel --region ${REGION} --cached --cache-dir ${BUILDDIR}/cache

deploy.guided: ##=> Guided deploy that is typically run for the first time only
	sam deploy --guided --template-file ${BUILDDIR}/template.yaml

deploy: ##=> Deploy app using previously saved SAM CLI configuration
	sam deploy --template-file ${BUILDDIR}/template.yaml --config-file ${PWD}/samconfig.toml

invoke: ##=> Run SAM Local function with a given event payload
	sam local invoke --event events/make_download.json -t ${BUILDDIR}/template.yaml --docker-network ${NETWORK}

#############
#  Helpers  #
#############

define HELP_MESSAGE
	Environment variables to be aware of or to hardcode depending on your use case:

	NETWORK
		Default: ""
		Info: Docker Network to connect to when running Lambda function locally

	Common usage:

	...::: Builds Lambda function dependencies:::...
	$ make build

	...::: Deploy for the first time :::...
	$ make deploy.guided

	...::: Deploy subsequent changes :::...
	$ make deploy

	...::: Cleans up the environment - Deletes Virtualenv, ZIP builds and Dev env :::...
	$ make clean
endef
