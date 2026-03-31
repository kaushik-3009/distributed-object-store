# Session 05: 24 March 2026

## Accomplishments
- Started Phase 4: Cloud Infrastructure (AWS & Terraform).
- Created `terraform/main.tf` to provision the VPC, Security Groups, ECR, and EC2 instance.
- Configured the EC2 instance to automatically install Docker and Docker Compose upon startup (`user_data` script).
- Created a new documentation file `docs/notes/aws_cloud.md` for learning the cloud components.

## Observations
- Using `t3.micro` ensures the demo stays within the AWS Free Tier.
- The `force_delete = true` on ECR repositories makes it easier to clean up the demo without manual intervention in the AWS Console.

## Things to Fix Next Time
- Need to finalize the Cloud IAM permissions so the EC2 instance can pull images from ECR.
- Need to create a `deploy.sh` script to automate the "build-push-deploy" workflow.
- Move to Phase 5: Filesystem Layer & Final Polish.
