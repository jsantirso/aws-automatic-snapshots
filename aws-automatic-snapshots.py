#!/usr/bin/python
"""
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


Copyright
---------
Joel Santirso, 2014


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
    #       - N: a new snapshot will be created for the period; the last N will be kept and the rest will be deleted
    'policies': {
        'CRITICAL': {
            'hour':  6,
            'day':   7,
            'week':  4,
            'month': 6
        },
        'MEH': {
            'hour':  0,
            'day':   2,
            'week':  1,
            'month': 0
        }
    },

    # (Optional) Path to the log file
    'log_file': '/home/ec2-user/aws-auto-snapshots.log',

}
# A tag that will be added to the snapshots
config['tag_period'] = '%s-PERIOD' % config['tag']


#
# LOGIC (DO NOT EDIT PAST THIS COMMENT)
#

def main():
    import boto.ec2
    import argparse
    from datetime import datetime, timedelta
    from collections import defaultdict
    import dateutil.parser
    import time
    import sys
    import logging

    try:
        # We get the period
        parser = argparse.ArgumentParser(
            description='A program that creates automatic AWS Volume snapshots. Read the script for more information.')
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

        #
        # We create the new snapshots
        #

        # We get the list of tags that must be processed this period
        logging.info('Policies (volume tag values) to snapshot:')
        policies_to_snapshot = [key for key, value in config['policies'].items() if value.get(period, None)]
        logging.info(', '.join(policies_to_snapshot))

        # We process each policy
        for policy in policies_to_snapshot:
            logging.info('Processing "%s"' % policy)

            # We get the volumes that have the policy
            volumes_to_snapshot = conn.get_all_volumes(filters={'tag:%s' % config['tag']: policy})
            logging.info('Volumes:')
            logging.info(', '.join(['%s (%sGiB)' % (vol.id, vol.size) for vol in volumes_to_snapshot]))

            # We process the volumes
            for vol in volumes_to_snapshot:
                try:
                    # We get its name
                    name_tags = conn.get_all_tags({'resource-id': vol.id, 'key': 'Name'})
                    name = name_tags[0].value if name_tags else '(un-named volume)'
                    logging.info('Creating the snapshot for %s (%sGiB - "%s")' % (vol.id, vol.size, name))
                    # We create the new snapshot for this policy and period
                    snap = vol.create_snapshot(
                        description='Automatic snapshot, period "%s"' % period
                    )
                    # We add some tags
                    conn.create_tags(
                        resource_ids=[snap.id],
                        tags={
                            # The name, which is based on the name of the volume
                            'Name': '[AS]%s' % name,
                            # The period
                            config['tag_period']: period
                        }
                    )
                except Exception, e:
                    logging.error('Error processing volume %s' % vol.id)
                    logging.error(e)
            logging.info('Done')

        logging.info('Finished creating the snapshots')

        #
        # We delete the old snapshots
        #

        logging.info('Deleting old snapshots')

        # We wait for a bit just in case Amazon needs some time to consolidate the new snapshots
        time.sleep(2)

        # We process the volumes that are managed by one of our auto-snapshot policies
        for policy in config['policies'].keys():
            for vol in conn.get_all_volumes(filters={'tag:%s' % config['tag']: policy}):
                try:
                    # We get its snapshots for the period we are processing
                    raw_snapshots = conn.get_all_snapshots(
                        owner='self',
                        filters={
                            'volume-id': vol.id,
                            'tag:%s' % config['tag_period']: period
                        }
                    )
                    logging.info('Processing volume %s (%sGiB, %s snapshot(s))' % (vol.id, vol.size, len(raw_snapshots)))
                    # We get which snapshots must be deleted, depending on the retention period configuration
                    if config['policies'][policy][period]:
                        sorted_snapshots = sorted(
                            raw_snapshots,
                            cmp=lambda x, y: cmp(
                                dateutil.parser.parse(x.start_time),
                                dateutil.parser.parse(y.start_time)
                            )
                        )
                        must_delete = sorted_snapshots[:-config['policies'][policy][period]]
                    else:
                        must_delete = raw_snapshots
                    if must_delete:
                        logging.info('Deleting %s snapshot(s)' % len(must_delete))
                        for snap in must_delete:
                            snap.delete()
                    else:
                        logging.info('Nothing to delete')
                    logging.info('Done')
                except Exception, e:
                    logging.error('Error processing volume %s (%sGiB)' % (vol.id, vol.size))
                    logging.error(e)

        logging.info('Finished deleting old snapshots')

    except Exception, e:
        logging.error('EXCEPTION: %s' % e)
        logging.error(sys.exc_info()[0])

if __name__ == '__main__':
    main()
