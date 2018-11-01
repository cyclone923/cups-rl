"""
Base class implementation for ai2thor environments wrapper, which adds an openAI gym interface for
inheriting the predefined methods and can be extended for particular tasks.
"""
import ai2thor.controller
import numpy as np
from skimage import transform
from copy import deepcopy

import gym
from gym import error, spaces
from gym.utils import seeding
from gym_ai2thor.image_processing import rgb2gray
from gym_ai2thor.utils import read_config
from gym_ai2thor.tasks import TaskFactory

ALL_POSSIBLE_ACTIONS = [
    'MoveAhead',
    'MoveBack',
    'MoveRight',
    'MoveLeft',
    'LookUp',
    'LookDown',
    'RotateRight',
    'RotateLeft',
    'OpenObject',
    'CloseObject',
    'PickupObject',
    'PutObject'
    # Teleport and TeleportFull but these shouldn't be allowable actions for an agent
]


class AI2ThorEnv(gym.Env):
    """
    Wrapper base class
    """
    def __init__(self, seed=None, config_file='config_files/config_example.ini', config_dict=None):
        """
        :param seed:         (int)   Random seed
        :param config_file:  (str)   Path to environment configuration file. Either absolute or
                                     relative path to the root of this repository.
        :param: config_dict: (dict)  Overrides specific fields from the input configuration file.
        """
        # Loads config settings from file
        self.config = read_config(config_file, config_dict)
        self.controller = ai2thor.controller.Controller()
        self.controller.start()
        # Randomness settings
        self.np_random = None
        if seed:
            self.seed(seed)
        # Create task from config
        self.task = TaskFactory.create_task(self.config)
        # Object settings
        # acceptable objects taken from config file.
        if self.config['env']['interaction']:
            self.objects = {'pickupables': self.config['env']['pickup_objects'],
                            'receptacles': self.config['env']['acceptable_receptacles'],
                            'openables':   self.config['env']['openable_objects']}
        # Action settings
        if self.config['env']['interaction']:
            self.action_names = tuple(ALL_POSSIBLE_ACTIONS.copy())
        else:
            self.action_names = tuple([action for action in ALL_POSSIBLE_ACTIONS
                                       if not action.endswith('Object')])
            # interactions end in 'Object'
        self.action_space = spaces.Discrete(len(self.action_names))
        # Image settings
        self.event = None
        channels = 1 if self.config['env']['grayscale'] else 3
        self.observation_space = spaces.Box(low=0, high=255,
                                            shape=(self.config['env']['resolution'][0],
                                                   self.config['env']['resolution'][1], channels),
                                            dtype=np.uint8)
        self.reset()

    def step(self, action, verbose=True):
        if not self.action_space.contains(action):
            raise error.InvalidAction('Action must be an integer between '
                                      '0 and {}!'.format(self.action_space.n))
        prev_state = deepcopy(self.event)
        action_str = self.action_names[action]
        visible_objects = [obj for obj in self.event.metadata['objects'] if obj['visible']]

        if action_str.endswith('Object'):  # All interactions end with 'Object'
            # Interaction actions
            interaction_obj, distance = None, float('inf')
            inventory_before = self.event.metadata['inventoryObjects'][0]['objectType'] \
                if self.event.metadata['inventoryObjects'] else []
            if action_str == 'PutObject':
                closest_receptacle = None
                for obj in visible_objects:
                    # look for closest receptacle to put object from inventory
                    if obj['receptacle'] and obj['distance'] < distance \
                        and obj in self.objects['receptacles'] \
                            and len(obj['receptacleObjectIds']) < obj['receptacleCount']:
                        closest_receptacle = obj
                        distance = closest_receptacle['distance']
                if self.event.metadata['inventoryObjects'] and closest_receptacle:
                    interaction_obj = closest_receptacle
                    self.event = self.controller.step(
                        dict(action=action_str,
                             objectId=self.event.metadata['inventoryObjects'][0],
                             receptacleObjectId=interaction_obj['objectId']))
            elif action_str == 'PickupObject':
                closest_pickupable = None
                for obj in visible_objects:
                    # look for closest object to pick up
                    if obj['pickupable'] and obj['distance'] < distance and \
                            obj['name'] in self.objects['pickupables']:
                        closest_pickupable = obj
                if closest_pickupable and not self.event.metadata['inventoryObjects']:
                    interaction_obj = closest_pickupable
                    self.event = self.controller.step(
                        dict(action=action_str,
                             objectId=interaction_obj['objectId']))
            elif action_str == 'OpenObject':
                closest_openable = None
                for obj in visible_objects:
                    # look for closest closed receptacle to open it
                    if obj['openable'] and obj['distance'] < distance and \
                            obj['name'] in self.objects['openables']:
                        closest_openable = obj
                        distance = closest_openable['distance']
                    if closest_openable:
                        interaction_obj = closest_openable
                        self.event = self.controller.step(
                            dict(action=action_str,
                                 objectId=interaction_obj['objectId']))
            elif action_str == 'CloseObject':
                closest_openable = None
                for obj in visible_objects:
                    # look for closest opened receptacle to close it
                    if obj['openable'] and obj['distance'] < distance and obj['isopen'] and \
                            obj['name'] in self.objects['openables']:
                        closest_openable = obj
                        distance = closest_openable['distance']
                    if closest_openable:
                        interaction_obj = closest_openable
                        self.event = self.controller.step(
                            dict(action=action_str,
                                 objectId=interaction_obj['objectId']))
            else:
                raise error.InvalidAction('Invalid interaction {}'.format(action_str))
            if interaction_obj and verbose:
                inventory_after = self.event.metadata['inventoryObjects'][0]['objectType'] \
                    if self.event.metadata['inventoryObjects'] else []
                print('{}: {}. Inventory before/after: {}/{}'.format(
                    action_str, interaction_obj['name'], inventory_before, inventory_after))
        else:
            # Move, Look or Rotate actions
            self.event = self.controller.step(dict(action=action_str))

        self.task.step_n += 1
        state_image = self.preprocess(self.event.frame)
        post_state = deepcopy(self.event)
        reward, done = self.task.transition_reward(prev_state, post_state)
        info = {}

        return state_image, reward, done, info

    def preprocess(self, img):
        """
        Compute image operations to generate state representation
        """
        img = transform.resize(img, self.config['env']['resolution'])
        img = img.astype(np.float32)
        if self.observation_space.shape[-1] == 1:
            img = rgb2gray(img)  # todo cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def reset(self):
        print('Resetting environment and starting new episode')
        self.controller.reset(self.config['env']['scene_id'])
        self.event = self.controller.step(dict(action='Initialize', gridSize=0.25,
                                               renderDepthImage=True, renderClassImage=True,
                                               renderObjectImage=True))
        self.task.reset()
        state = self.preprocess(self.event.frame)
        return state

    def render(self, mode='human'):
        raise NotImplementedError

    def seed(self, seed=None):
        self.np_random, seed1 = seeding.np_random(seed)
        # Derive a random seed. This gets passed as a uint, but gets
        # checked as an int elsewhere, so we need to keep it below
        # 2**31.
        return seed1

    def close(self):
        pass


if __name__ == '__main__':
    AI2ThorEnv()
