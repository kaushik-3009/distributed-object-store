# Cloud Infrastructure Concepts (AWS + Terraform)

## What is Terraform?
Terraform is an **Infrastructure as Code (IaC)** tool. Instead of manually creating servers in the AWS dashboard, we write a text file (`main.tf`) that describes exactly what we want. 

Advantages:
1. **Reproducibility**: We can delete the whole setup and recreate it exactly as it was in minutes.
2. **Speed**: No more clicking through 50 menus.

## Core AWS Components used in this project:

### 1. VPC (Virtual Private Cloud)
A private network in the cloud that is logically isolated from other networks. It’s like your own personal data center in AWS.

### 2. ECR (Elastic Container Registry)
A private storage area for Docker images. We "push" our local Coordinator and Node images here, and then our AWS server "pulls" them to run them.

### 3. EC2 (Elastic Compute Cloud)
This is the actual **Virtual Machine (VM)**. We are using a `t3.micro` which is free-tier eligible. It runs a version of Linux (Amazon Linux 2023).

### 4. Security Groups
These are **firewalls**. We only open the specific ports we need (8000 for Coordinator, 22 for SSH). This keeps the system secure from random bots on the internet.

### 5. IAM Roles (Identity and Access Management)
These define what our EC2 server is "allowed" to do. In our case, the EC2 server needs permission to "talk" to the ECR registry to download our code.

## The Deployment Workflow
1. Use Terraform to "Spin up" the AWS resources.
2. Build our local Docker images and push them to ECR.
3. SSH into the EC2 instance.
4. Run `docker-compose up` to start our sharded object store in the cloud!
