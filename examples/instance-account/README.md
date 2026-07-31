# Example: one instance account

Deploys the reporter into a single AWS account and region, together with the
prerequisites it expects to find: an ECS exec logs bucket that emits EventBridge
notifications, the KMS key that bucket is encrypted with, and a Secrets Manager
container for the Kosli API token.

In a real deployment those prerequisites already exist — in Kosli's case in
`terraform-base-infra` — so only the `module` block and the secret container are
new.

Two things this example cannot show, because they live outside the AWS account:

- **The flow must exist first.** `infra-dev-instance-access` is declared in
  `terraform-kosli-app`, once per Kosli instance. The reporter begins trails in
  that flow; it does not create it.
- **The secret must be populated.** Terraform creates the container with no
  version. Until a token is put in it, `GetSecretValue` fails at runtime, the
  lambda errors, and the error alarm fires.

Run it with:

```console
terraform init
terraform plan
```

Note that this example creates real resources, including two Lambda functions.
Run `terraform destroy` when you are finished with it.
