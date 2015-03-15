#!/usr/bin/python
"""
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
This projected is licensed under the terms of the MIT license."""


#
# CONFIGURATION (EDIT THIS SECTION)
#

config = {
    'user': {
        # AWS credentials for the IAM user that will create the snapshots (passed directly to boto's connection)
        'aws_access_key': '',
        'aws_secret_key': ''
    },

    # The name of the ec2 region where the volumes reside
    'ec2_region': 'us-west-1',

    # The name of the tag that must be assigned to the volumes (the value must be the name of one of the policies)
    'tag': 'AUTO-SNAPSHOT',

    # Snapshot/Backup policies:
    #   - The name is arbitrary
    #   - The value defines the creation and retention of snapshots for each time period (hour, day, week and month)
    #       - 0: no snapshot will be created for that period, and old snapshots will be deleted
    #       - N: a new snapshot will be created for the period, the last N will be kept, and the rest will be deleted
    #   - The optional key "only_attached_vols" can be used to only make snapshots of volumes attached to the current
    #     instance.
    #     This is useful to create multiple instances from an AMI that has automatic-snapshots configured: if not set
    #     every instance would snapshot every volume, resulting in multiple copies of the same data
    'policies': {
        'CRITICAL': {
            'hour':   2,
            'day':    5,
            'week':  52,
            'month':  0,
            'only_attached_vols': True
        },
        'MEH': {
            'hour':   0,
            'day':    0,
            'week':   0,
            'month':  1,
            'only_attached_vols': True
        }
    },

    # (Optional) Path to the log file
    # 'log_file': '/home/ec2-user/aws-auto-snapshots.log'

}
# A tag that will be added to the snapshots
config['tag_period'] = '%s-PERIOD' % config['tag']


#
# LOGIC (DO NOT EDIT PAST THIS COMMENT)
#

def main():
    from datetime import datetime, timedelta
    from collections import defaultdict
    import dateutil.parser
    import boto.utils
    import boto.ec2
    import traceback
    import argparse
    import logging
    import time
    import imp
    import sys
    import os

    try:
        # We get the period
        parser = argparse.ArgumentParser(
            description='A program that creates automatic AWS Volume snapshots. Read the script for more information.'
        )
        parser.add_argument('period', choices=('hour', 'day', 'week', 'month'))
        period = parser.parse_args().period

        # We setup the logging
        logging.basicConfig(
            filename=config.get('log_file', None) or None,
            level=logging.INFO,
            format='[%(asctime)s] %(message)s')

        # We start the process
        logging.info('PROCESSING A NEW PERIOD: "%s"' % period)

        # We connect to aws
        conn = boto.ec2.connect_to_region(
            region_name=config['ec2_region'],
            aws_access_key_id=config['user']['aws_access_key'],
            aws_secret_access_key=config['user']['aws_secret_key']
        )
        logging.info('Connected to aws')

        # We get the current instance's metadata
        instance_metadata = boto.utils.get_instance_metadata()

        # We cache the volumes affected by each policy
        volumes_to_process = {}
        for policy, settings in config['policies'].iteritems():
            volume_filters = {'tag:%s' % config['tag']: policy}
            if settings.get('only_attached_vols', False):
                volume_filters['attachment.instance-id'] = instance_metadata['instance-id']
            volumes_to_process[policy] = conn.get_all_volumes(filters=volume_filters)

        #
        # We create the new snapshots
        #

        logging.info('Creating the snapshots for each policy:')
        policies_to_snapshot = [(p, s) for p, s in config['policies'].iteritems() if s.get(period, None)]
        for policy, settings in policies_to_snapshot:
            logging.info(
                'Processing "%s" (only_attached_vols: %s)' %
                (policy, settings.get('only_attached_vols', False))
            )
            for vol in volumes_to_process[policy]:
                hook_module_path = settings.get('hook_module', None)
                hook_module = None
                snap = None
                try:
                    # We create the new snapshot for this policy and period
                    logging.info(
                        'Creating the snapshot for %s ("%s", %sGiB)' %
                        (vol.id, vol.tags.get('Name', ''), vol.size)
                    )
                    if hook_module_path:
                        logging.info('Loading the hook module (%s)' % hook_module_path)
                        hook_module = imp.load_source('hook_module', hook_module_path)
                            # If the module was already initialized, it will be initialized again
                        logging.info('Executing hook (before)')
                        hook_module.aws_automatic_snapshots_before(period, policy, vol)
                        logging.info('Done')

                    snap = vol.create_snapshot(description='Automatic snapshot, period "%s"' % period)
                    conn.create_tags(
                        resource_ids=[snap.id],
                        tags={
                            # The name, which is based on the name of the volume
                            'Name': '[AS]%s' % vol.tags.get('Name', ''),
                            # The period
                            config['tag_period']: period
                        }
                    )
                    logging.info('Snapshot created')
                except Exception, e:
                    logging.error('Error processing volume %s' % vol.id)
                    logging.error(traceback.format_exc())
                finally:
                    try:
                        if hook_module_path and hook_module:
                            logging.info('Executing hook (after)')
                            hook_module.aws_automatic_snapshots_after(period, policy, vol, snap)
                            logging.info('Done')
                    except Exception, e:
                        logging.error('Error executing the hooks')
                        logging.error(traceback.format_exc())

        if policies_to_snapshot:
            # We wait for a bit just in case Amazon needs some time to consolidate the new snapshots
            time.sleep(5)
        else:
            logging.info('No policies required snapshots for this period')

        #
        # We delete the old snapshots
        #

        logging.info('Deleting old snapshots for this period:')

        # We process the volumes that are managed by one of our auto-snapshot policies
        for policy, settings in config['policies'].iteritems():
            for vol in volumes_to_process[policy]:
                try:
                    # We get its snapshots for the period we are processing
                    raw_snapshots = conn.get_all_snapshots(
                        owner='self',
                        filters={
                            'volume-id': vol.id,
                            'tag:%s' % config['tag_period']: period
                        }
                    )
                    logging.info(
                        'Processing volume %s ("%s", %sGiB, %s snapshot(s))' %
                        (vol.id, vol.tags.get('Name', ''), vol.size, len(raw_snapshots))
                    )
                    # We get which snapshots must be deleted, depending on the retention period configuration
                    if settings.get(period, None):
                        sorted_snapshots = sorted(
                            raw_snapshots,
                            cmp=lambda x, y: cmp(
                                dateutil.parser.parse(x.start_time),
                                dateutil.parser.parse(y.start_time)
                            )
                        )
                        must_delete = sorted_snapshots[:-settings[period]]
                    else:
                        must_delete = raw_snapshots
                    if must_delete:
                        logging.info('Deleting %s snapshot(s)' % len(must_delete))
                        for snap in must_delete:
                            snap.delete()
                        logging.info('Done')
                    else:
                        logging.info('Nothing to delete')
                except Exception, e:
                    logging.error(
                        'Error processing volume %s ("%s", %sGiB)' %
                        (vol.id, vol.tags.get('Name', ''), vol.size)
                    )
                    logging.error(traceback.format_exc())

        logging.info('FINISHED PROCESSING THE PERIOD')

    except Exception, e:
        logging.error(traceback.format_exc())

if __name__ == '__main__':
    main()