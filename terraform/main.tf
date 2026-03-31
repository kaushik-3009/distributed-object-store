# --- AWS Provider ---
provider "aws" {
  region = "us-east-1" # You can change this to your preferred region
}

# --- VPC (Virtual Private Cloud) ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "sec-dist-vpc" }
}

# --- Internet Gateway (To allow traffic in/out) ---
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}

# --- Public Subnet ---
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
}

# --- Route Table (How traffic gets to the Internet) ---
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}

resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public_rt.id
}

# --- Security Group (Firewall) ---
resource "aws_security_group" "allow_web" {
  name        = "allow_web_traffic"
  description = "Allow inbound traffic on ports 8000-8003"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 8000
    to_port     = 8003
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # In a real system, you'd restrict this to YOUR IP
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # For SSH access
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- ECR (Docker Registries) ---
resource "aws_ecr_repository" "coordinator" {
  name = "coordinator-repo"
  force_delete = true
}

resource "aws_ecr_repository" "node" {
  name = "node-repo"
  force_delete = true
}

# --- EC2 (The Server) ---
resource "aws_instance" "app_server" {
  ami           = "ami-0c7217cdde317cfec" # Amazon Linux 2023 AMI (us-east-1)
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.allow_web.id]
  
  # We'll need a way to log in. In Phase 4, we'll talk about keys.
  key_name = "deployer-key" 

  tags = { Name = "sec-dist-server" }

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y docker
              service docker start
              usermod -a -G docker ec2-user
              # Install Docker Compose
              curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
              chmod +x /usr/local/bin/docker-compose
              EOF
}

output "server_public_ip" {
  value = aws_instance.app_server.public_ip
}
