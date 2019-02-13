* create an EC2 key pair
* also see https://github.com/binxio/cfn-kong-provider
* create stack for Kong:

    ```
    aws --region us-east-1 cloudformation create-stack \
        --stack-name kong-environment \
        --capabilities CAPABILITY_IAM \
        --template-body file://kong.yaml \
        --parameters ParameterKey=KongKeyName,ParameterValue=<key-pair-name>

    ```

* get Kong AdminURL:

    ```
    ADMIN_URL=$(aws --region us-east-1 --output text \
        --query 'Stacks[*].Outputs[?OutputKey==`AdminURL`].OutputValue' \
        cloudformation describe-stacks --stack-name kong-environment)
    ```

* install the providers:

    ```
    aws --region us-east-1 cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name cfn-kong-provider \
        --template-body file://cfn-resource-provider.yaml
    ```

* create/update Kong objects:

    ```
    aws --region us-east-1 cloudformation create-stack \
        --stack-name kong-objects \
        --template-body file://kong-objects.yaml \
        --parameters ParameterKey=AdminURL,ParameterValue=$ADMIN_URL
    ```
