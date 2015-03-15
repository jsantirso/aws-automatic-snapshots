AWS Automatic Snapshots
=======================

This script performs automatic snapshots (backups) of tagged EBS volumes, with configurable periodicity and retention
policies.


Features
--------
- Easy to use, it leverages **AWS's tags** to select the volumes to back up
- Written in **Python**, it's easy to customize and install using Cron
- It support **"before" and "after" hooks**, which can be used to lock and unlock a database or filesystem
- It supports **unlimited**, **fine-grained** custom policies. For example:
```
    {
        "CRITICAL": {     # Tag your data volume as "AUTO-SNAPSHOT" : "CRITICAL" to activate the automatic backups
            "hour":   2,  # Create a snapshot each hour, keep the last two, and delete the rest
            "day":    5,  # Create a snapshot each day, keep the last five, and delete the rest
            "week":  52,  # Create a snapshot each week, keep the last 52, and delete the rest
            "month":  0,  # Don't make a monthly snapshot, and delete any existing snapshots for this policy and period
            "only_attached_vols": True,  # Only snapshot volumes which are attached to the current instance
            "hook_module": "/usr/local/bin/flush_and_lock_mysql.py"  # A module with "before" and "after" hooks
        },
        "MEH": {
            "hour":   0,
            "day":    0,
            "week":   0,
            "month":  1,
            "only_attached_vols": True,
            "hook_module": None
        },
        ...
    }
```

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


- Optionally, create a Python script that defines the following functions:
```
    aws_automatic_snapshots_before(period, policy, volume)
    aws_automatic_snapshots_after(period, policy, volume, snapshot)
```


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


Copyright
---------
Joel Santirso, 2015


License
-------
This projected is licensed under the terms of the MIT license.