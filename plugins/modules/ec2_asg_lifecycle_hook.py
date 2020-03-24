#!/usr/bin/python

# Copyright: (c) 2017, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'metadata_version': '1.1'}

DOCUMENTATION = '''
---
module: ec2_asg_lifecycle_hook
short_description: Create, delete or update AWS ASG Lifecycle Hooks.
description:
  - Will create a new hook when I(state=present) and no given Hook is found.
  - Will update an existing hook when I(state=present) and a Hook is found, but current and provided parameters differ.
  - Will delete the hook when I(state=absent) and a Hook is found.
author: Igor 'Tsigankov' Eyrich (@tsiganenok) <tsiganenok@gmail.com>
options:
  state:
    description:
      - Create or delete Lifecycle Hook.
      - When I(state=present) updates existing hook or creates a new hook if not found.
    choices: ['present', 'absent']
    default: present
    type: str
  lifecycle_hook_name:
    description:
      - The name of the lifecycle hook.
    required: true
    type: str
  autoscaling_group_name:
    description:
      - The name of the Auto Scaling group to which you want to assign the lifecycle hook.
    required: true
    type: str
  transition:
    description:
      - The instance state to which you want to attach the lifecycle hook.
      - Required when I(state=present).
    choices: ['autoscaling:EC2_INSTANCE_TERMINATING', 'autoscaling:EC2_INSTANCE_LAUNCHING']
    type: str
  role_arn:
    description:
      - The ARN of the IAM role that allows the Auto Scaling group to publish to the specified notification target.
    type: str
  notification_target_arn:
    description:
      - The ARN of the notification target that Auto Scaling will use to notify you when an
        instance is in the transition state for the lifecycle hook.
      - This target can be either an SQS queue or an SNS topic.
      - If you specify an empty string, this overrides the current ARN.
    type: str
  notification_meta_data:
    description:
      - Contains additional information that you want to include any time Auto Scaling sends a message to the notification target.
    type: str
  heartbeat_timeout:
    description:
      - The amount of time, in seconds, that can elapse before the lifecycle hook times out.
        When the lifecycle hook times out, Auto Scaling performs the default action.
        You can prevent the lifecycle hook from timing out by calling RecordLifecycleActionHeartbeat.
      - By default Amazon AWS will use 3600 (1 hour)
    type: int
  default_result:
    description:
      - Defines the action the Auto Scaling group should take when the lifecycle hook timeout
        elapses or if an unexpected failure occurs.
    choices: ['ABANDON', 'CONTINUE']
    default: ABANDON
    type: str
extends_documentation_fragment:
- ansible.amazon.aws
- ansible.amazon.ec2

requirements: [ boto3>=1.4.4 ]

'''

EXAMPLES = '''
# Create / Update lifecycle hook
- ec2_asg_lifecycle_hook:
    region: eu-central-1
    state: present
    autoscaling_group_name: example
    lifecycle_hook_name: example
    transition: autoscaling:EC2_INSTANCE_LAUNCHING
    heartbeat_timeout: 7000
    default_result: ABANDON

# Delete lifecycle hook
- ec2_asg_lifecycle_hook:
    region: eu-central-1
    state: absent
    autoscaling_group_name: example
    lifecycle_hook_name: example

'''

RETURN = '''

'''

from ansible_collections.ansible.amazon.plugins.module_utils.aws.core import AnsibleAWSModule

try:
    import botocore
except ImportError:
    pass  # handled by AnsibleAWSModule


def create_lifecycle_hook(connection, module):
    changed = False

    lch_name = module.params.get('lifecycle_hook_name')
    asg_name = module.params.get('autoscaling_group_name')
    transition = module.params.get('transition')
    role_arn = module.params.get('role_arn')
    notification_target_arn = module.params.get('notification_target_arn')
    notification_meta_data = module.params.get('notification_meta_data')
    heartbeat_timeout = module.params.get('heartbeat_timeout')
    default_result = module.params.get('default_result')

    lch_params = {
        'LifecycleHookName': lch_name,
        'AutoScalingGroupName': asg_name,
        'LifecycleTransition': transition
    }

    if role_arn:
        lch_params['RoleARN'] = role_arn

    if notification_target_arn:
        lch_params['NotificationTargetARN'] = notification_target_arn

    if notification_meta_data:
        lch_params['NotificationMetadata'] = notification_meta_data

    if heartbeat_timeout:
        lch_params['HeartbeatTimeout'] = heartbeat_timeout

    if default_result:
        lch_params['DefaultResult'] = default_result

    try:
        existing_hook = connection.describe_lifecycle_hooks(
            AutoScalingGroupName=asg_name,
            LifecycleHookNames=[lch_name]
        )['LifecycleHooks']
    except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
        module.fail_json_aws(e, msg="Failed to get Lifecycle Hook")

    if not existing_hook:
        changed = True
    else:
        # GlobalTimeout is not configurable, but exists in response.
        # Removing it helps to compare both dicts in order to understand
        # what changes were done.
        del(existing_hook[0]['GlobalTimeout'])
        added, removed, modified, same = dict_compare(lch_params, existing_hook[0])
        if added or removed or modified:
            changed = True

    if changed:
        try:
            connection.put_lifecycle_hook(**lch_params)
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
            module.fail_json_aws(e, msg="Failed to create LifecycleHook")

    return(changed)


def dict_compare(d1, d2):
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    intersect_keys = d1_keys.intersection(d2_keys)
    added = d1_keys - d2_keys
    removed = d2_keys - d1_keys
    modified = False
    for key in d1:
        if d1[key] != d2[key]:
            modified = True
            break

    same = set(o for o in intersect_keys if d1[o] == d2[o])
    return added, removed, modified, same


def delete_lifecycle_hook(connection, module):
    changed = False

    lch_name = module.params.get('lifecycle_hook_name')
    asg_name = module.params.get('autoscaling_group_name')

    try:
        all_hooks = connection.describe_lifecycle_hooks(
            AutoScalingGroupName=asg_name
        )
    except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
        module.fail_json_aws(e, msg="Failed to get Lifecycle Hooks")

    for hook in all_hooks['LifecycleHooks']:
        if hook['LifecycleHookName'] == lch_name:
            lch_params = {
                'LifecycleHookName': lch_name,
                'AutoScalingGroupName': asg_name
            }

            try:
                connection.delete_lifecycle_hook(**lch_params)
                changed = True
            except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
                module.fail_json_aws(e, msg="Failed to delete LifecycleHook")
        else:
            pass

    return(changed)


def main():
    argument_spec = dict(
        autoscaling_group_name=dict(required=True, type='str'),
        lifecycle_hook_name=dict(required=True, type='str'),
        transition=dict(type='str', choices=['autoscaling:EC2_INSTANCE_TERMINATING', 'autoscaling:EC2_INSTANCE_LAUNCHING']),
        role_arn=dict(type='str'),
        notification_target_arn=dict(type='str'),
        notification_meta_data=dict(type='str'),
        heartbeat_timeout=dict(type='int'),
        default_result=dict(default='ABANDON', choices=['ABANDON', 'CONTINUE']),
        state=dict(default='present', choices=['present', 'absent'])
    )

    module = AnsibleAWSModule(argument_spec=argument_spec,
                              required_if=[['state', 'present', ['transition']]])
    state = module.params.get('state')

    connection = module.client('autoscaling')

    changed = False

    if state == 'present':
        changed = create_lifecycle_hook(connection, module)
    elif state == 'absent':
        changed = delete_lifecycle_hook(connection, module)

    module.exit_json(changed=changed)


if __name__ == '__main__':
    main()