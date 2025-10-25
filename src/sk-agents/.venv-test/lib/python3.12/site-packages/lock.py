# -*- coding: utf-8 -*-

"""
################################################################################
#                                                                              #
# lock                                                                         #
#                                                                              #
################################################################################
#                                                                              #
# LICENCE INFORMATION                                                          #
#                                                                              #
# This program provides file locking and JSON saving and loading utilities.    #
#                                                                              #
# copyright (C) 2018 William Breaden Madden, Gavin Kirby                       #
#                                                                              #
# This software is released under the terms of the GNU General Public License  #
# version 3 (GPLv3).                                                           #
#                                                                              #
# This program is free software: you can redistribute it and/or modify it      #
# under the terms of the GNU General Public License as published by the Free   #
# Software Foundation, either version 3 of the License, or (at your option)    #
# any later version.                                                           #
#                                                                              #
# This program is distributed in the hope that it will be useful, but WITHOUT  #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or        #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for     #
# more details.                                                                #
#                                                                              #
# For a copy of the GNU General Public License, see                            #
# <http://www.gnu.org/licenses/>.                                              #
#                                                                              #
################################################################################
"""

import fcntl
import json
import time

__version__ = "2018-03-25T2110Z"

def lock(filepath):
    lock_file = open(filepath, "a")
    try:
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as error:
        return error
    return lock_file

def unlock(filepath):
    lock_file = open(filepath, "a")
    try:
        fcntl.lockf(lock_file, fcntl.LOCK_UN)
    except (OSError, BlockingIOError) as error:
        return error
    return lock_file

def save_JSON(filepath, dictionary, hang_until_unlocked = True, indent = 4):
    if lock(filepath):
        with open(filepath, "w") as file_JSON:
            json.dump(dictionary, file_JSON, indent = indent)
        unlock(filepath)
        return True
    elif hang_until_unlocked:
        while not lock(filepath):
            time.sleep(0.1)
        with open(filepath, "w") as file_JSON:
            json.dump(dictionary, file_JSON)
        unlock(filepath)
        return True
    else:
        return False

def load_JSON(filepath, hang_until_unlocked = True):
    if lock(filepath):
        try:
            with open(filepath) as file_JSON:
                dictionary = json.load(file_JSON)
            unlock(filepath)
            return dictionary
        except:
            return False
    elif hang_until_unlocked:
        while not lock(filepath):
            time.sleep(0.1)
        try:
            with open(filepath) as file_JSON:
                dictionary = json.load(file_JSON)
            unlock(filepath)
            return dictionary
        except:
            return False
    else:
        return False
