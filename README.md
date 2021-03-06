# AutoBlock Bot
AutoBlock Bot is a telegram bot that listens for joins, and checks new members against a database of globally banned users. When one of those users enters a chat, the bot kicks the user from the chat.

## Repository contents
- autoblock_function - Code for the application's Lambda function.
- events - Invocation events that you can use to invoke the function.
- tests - Unit tests for the application code. 
- template.yaml - A template that defines the application's AWS resources.

## Systems Manager Parameters
The autoblock function reads its bot key from the `/autoblock_bot/bot_key` parameter. It expects the contents of the parameter to be only the string value of the bot api key.

## Database format
The database storage for the block bot is split into two parts: the part in S3, and the part in DynamoDB. Part of the configuration is relatively small and rarely changes, so loading it all into memory is reasonable. This part is stored in S3, and loaded once when the lambda starts up. The part in DynamoDB changes slightly more frequently, but more importantly, is much bigger: the list of users and their associated roles.

### Roles and rooms configuration
S3 will store a JSON document with one property: the set of users who can administer the bots.

```json
{
  "root": ["999999999", "888888888"]
}
```

### Users and associated roles
Users and their associated roles are stored in DynamoDB. Associations between users and roles are stored as items that represent that relationship, as well as its inverse.

```json
{
  "pk": "user_99999999",
  "sk": "user_99999999",
  "username": "@username"
}
```

The inverse relationship is calculated by a secondary index with `role_users_pk` as its partition key, and `role_users_sk` as its sort key.
```json
{
  "pk": "user_99999999",
  "sk": "role_whitelist",
  "role_users_pk": "role_whitelist",
  "role_users_sk": "user_99999999"
}
```

## Deploy the application
The Serverless Application Model Command Line Interface (SAM CLI) is an extension of the AWS CLI that adds functionality for building and testing Lambda applications. It uses Docker to run your functions in an Amazon Linux environment that matches Lambda. It can also emulate your application's build environment and API.

To use the SAM CLI, you need the following tools.

* AWS CLI - [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html) and [configure it with your AWS credentials].
* SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* [Python 3 installed](https://www.python.org/downloads/)
* Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community)

The SAM CLI uses an Amazon S3 bucket to store your application's deployment artifacts. If you don't have a bucket suitable for this purpose, create one. Replace `BUCKET_NAME` in the commands in this section with a unique bucket name.

```bash
sam-app$ aws s3 mb s3://BUCKET_NAME
```

To prepare the application for deployment, use the `sam package` command.

```bash
sam-app$ sam package \
    --output-template-file packaged.yaml \
    --s3-bucket BUCKET_NAME
```

The SAM CLI creates deployment packages, uploads them to the S3 bucket, and creates a new version of the template that refers to the artifacts in the bucket. 

To deploy the application, use the `sam deploy` command.

```bash
sam-app$ sam deploy \
    --template-file packaged.yaml \
    --stack-name autoblock-bot \
    --capabilities CAPABILITY_IAM
```

After deployment is complete you can run the following command to retrieve the API Gateway Endpoint URL:

```bash
sam-app$ aws cloudformation describe-stacks \
    --stack-name autoblock-bot \
    --query 'Stacks[].Outputs[?OutputKey==`AutoBlockApi`]' \
    --output table
``` 

## Use the SAM CLI to build and test locally
Build your application with the `sam build` command.

```bash
sam-app$ sam build
```

The SAM CLI installs dependencies defined in `autoblock_bot/requirements.txt`, creates a deployment package, and saves it in the `.aws-sam/build` folder.

Test a single function by invoking it directly with a test event. An event is a JSON document that represents the input that the function receives from the event source. Test events are included in the `events` folder in this project.

Run functions locally and invoke them with the `sam local invoke` command.

```bash
sam-app$ sam local invoke AutoBlockFunction --event events/message.json
```

The SAM CLI can also emulate your application's API. Use the `sam local start-api` to run the API locally on port 3000.

```bash
sam-app$ sam local start-api
sam-app$ curl http://localhost:3000/
```

The SAM CLI reads the application template to determine the API's routes and the functions that they invoke. The `Events` property on each function's definition includes the route and method for each path.

```yaml
      Events:
        HelloWorld:
          Type: Api
          Properties:
            Path: /hello
            Method: get
```

## Add a resource to your application
The application template uses AWS Serverless Application Model (AWS SAM) to define application resources. AWS SAM is an extension of AWS CloudFormation with a simpler syntax for configuring common serverless application resources such as functions, triggers, and APIs. For resources not included in [the SAM specification](https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md), you can use standard [AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) resource types.

## Fetch, tail, and filter Lambda function logs
To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
sam-app$ sam logs -n AutoBlockFunction --stack-name autoblock-bot --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).

## Unit tests

Tests are defined in the `tests` folder in this project. Use PIP to install the [pytest](https://docs.pytest.org/en/latest/) and run unit tests.

```bash
sam-app$ pip install pytest pytest-mock --user
sam-app$ python -m pytest tests/ -v
```

## Resources
See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to SAM specification, the SAM CLI, and serverless application concepts.

Next, you can use AWS Serverless Application Repository to deploy ready to use Apps that go beyond hello world samples and learn how authors developed their applications: [AWS Serverless Application Repository main page](https://aws.amazon.com/serverless/serverlessrepo/)
