AWS Automatic Snapshots
=======================

This script performs automatic snapshots (backups) of tagged EBS volumes, with configurable periodicity and retention policies.


Features
--------
- Easy to use, it leverages **AWS's tags** to select the volumes to back up
- Written in **Python**, it's easy to customize and install using Cron
- It supports **unlimited**, **fine-grained** custom policies

Usage
-----
- Create the following IAM policy using the AWS Console and assign it to a user:

```
    {
        "Statement": [
            {
                "Sid": "Stmtxxxxxxxxxxxxx",
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateSnapshot",
                    "ec2:CreateTags",
                    "ec2:DeleteSnapshot",
                    "ec2:DescribeSnapshots",
                    "ec2:DescribeTags",
                    "ec2:DescribeVolumeAttribute",
                    "ec2:DescribeVolumeStatus",
                    "ec2:DescribeVolumes"
                ],
                "Resource": [
                    "*"
                ]
            }
        ]
    }
```


- Edit the script and customize the configuration

- Tag your EBS Volumes with the policies you have defined. For example: ```"AUTO-SNAPSHOTS"``` : ```"CRITICAL"```

- Edit Crontab to execute your script periodically:

```
# chmod +x aws-automatic-snapshots.py
# crontab -e
@hourly /usr/local/bin/aws-automatic-snapshots.py hour
@daily /usr/local/bin/aws-automatic-snapshots.py day
@weekly /usr/local/bin/aws-automatic-snapshots.py week
@monthly /usr/local/bin/aws-automatic-snapshots.py month
```
	
Dependencies
------------
- [boto](https://pypi.python.org/pypi/boto/)
- [python-dateutil](https://pypi.python.org/pypi/python-dateutil)



**Copyright** (c) 2014 Joel Santirso

**License**: MIT