"""
Auxiliary functions for building environments
"""
import os
import configparser

from gym import error


def read_config(config_path, config_dict=None):
    """
    Returns the parsed information from the config file
    """
    config_path = os.path.join(os.path.dirname(__file__), config_path)
    config = configparser.ConfigParser()
    config_output = config.read(config_path)
    if not config_output:
        raise error.Error('No config file found at: {}. Exiting'.format(config_path))
    config_output = {'env': {'interaction': True,
                             'pickup_objects': ['Mug', 'Apple', 'Book'],
                             'acceptable_receptacles': ['CounterTop', 'TableTop', 'Sink'],
                             'openable_objects': ['Microwave'],
                             'scene_id': 'FloorPlan28',
                             'grayscale': True,
                             'resolution': (300, 300)},
                     'task': {'task_name': 'PickUp',
                              'target_object': 'Mug'}}
    return config_output

class InvalidTaskParams(Exception):
    """
    Raised when the user inputs the wrong parameters for creating a task.
    """
    pass
