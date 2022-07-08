#!/usr/bin/python3
"""
AutoPkg Runner: Execution Script

__author__    = "Ellis Dickinson"
__copyright__ = "Copyright 2022, ByteFloater"
__license__   = "Apache"
__version__   = "0.5.0"
__status__    = "Production"

See README.md for more information
"""

import atexit
import gc
import os
import plistlib
import socket
import subprocess
import urllib.parse

from helpers import notify
from helpers.logger import logger

# Flags
AUTOPKG_DEBUG = True
REPORT_DEBUG = False


class AutoPkgRunner:
    """See module docstring"""
    def __init__(self):
        self.did_create_dir = False
        self.remote_did_mount = False
        self.send_pushover = False
        self.recipe_list = []

        # Import the script preferences file
        with open("script_settings.plist", 'rb') as plist_file:
            self.prefs = plistlib.load(plist_file)

        samba_prefs = self.prefs["SambaSettings"]
        script_settings = self.prefs["ScriptSettings"]
        recipe_list_path_raw = script_settings["RecipeListPath"]

        # Construct the correct URL format for mount_smbfs
        self.remote_addr = self.construct_url(
            srv_addr=samba_prefs["ConnectionAddress"],
            srv_user=samba_prefs["CredentialsUser"],
            srv_pass=samba_prefs["CredentialsPass"],
            srv_share=samba_prefs["ServerShare"]
        )

        # Create the recipe list to be executes by AutoPkg
        recipe_list_path = os.path.expanduser(recipe_list_path_raw)
        with open(recipe_list_path, 'r', encoding='utf-8') as recipe_list_file:
            for recipe in recipe_list_file:
                self.recipe_list.append(recipe.strip())

        # Set the location of the AutoPkg report data
        apkg_report_loc = script_settings["ReportPlistDir"] + "/autopkg_report.plist"
        if not REPORT_DEBUG:
            report_loc = apkg_report_loc
        else:
            logger("REPORT_DEBUG set to True, using example data")
            report_loc = f"{os.getcwd()}/sample_data/example_data.plist"
        
        self.apkg_report_dir = os.path.expanduser(apkg_report_loc)
        self.report_location = os.path.expanduser(report_loc)

        atexit.register(self.cleanup)

    def is_server_available(self, connection_addr: str) -> bool:
        """
        Check the availability of a given server

        Parameters:
            connection_addr (str): mDNS Address

        Returns:
            1 - Server Available
            0 - Server Unavailable
        """
        logger("Checking serer availability...")
        split = connection_addr.split('.')
        test_addr = '.'.join([split[0], split[-1]])

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((test_addr, 445))

        return bool(result == 0)

    def construct_url(self,
                      srv_user: str,
                      srv_pass: str,
                      srv_addr: str,
                      srv_share: str) -> str:
        """Build the correct address format for mount_smbfs"""
        repo_url = f"//{srv_user}:{srv_pass}@{srv_addr}/{srv_share}"
        return urllib.parse.quote(repo_url, safe="/:@")

    def prepare_remote(self, remote_addr: str):
        """Create the server mount point and mount the Munki Repository"""
        try:
            logger("Attempting to create mount point...")
            os.mkdir(self.prefs["LocalMountPoint"])
            self.did_create_dir = True

            logger("Attempting to mount...")
            subprocess.check_call([
                "mount_smbfs",
                remote_addr,
                self.prefs["LocalMountPoint"]
            ])
            self.remote_did_mount = True
        except FileExistsError as err:
            logger("Failed to prepare remote: " + str(err))
        except subprocess.CalledProcessError as err:
            logger("Failed to prepare remote: " + str(err))

    def repo_integrity_check(self) -> bool:
        """Check for the existence of the skeleton repository structure"""
        logger("Performing repository integrity check...")
        for _dir in self.prefs["CheckDirs"]:
            logger(f"Checking for: {_dir}", 1)
            test_path = f"{self.prefs['LocalMountPoint']}/{_dir}"
            if not os.path.isdir(test_path):
                logger(f"Unable to find: {_dir}")
                return False

        return True

    def run_autopkg(self, *args):
        """Launch AutoPkg and run all the recipes in the recipe list"""
        logger("Attempting to run AutoPkg...")
        try:
            subprocess.check_call([
                self.prefs["AutoPkgPath"],
                "run",
                *self.recipe_list,
                "--report-plist",
                self.apkg_report_dir,
                "-q",
                "-k",
                f"MUNKI_REPO={self.prefs['LocalMountPoint']}",
                *args
            ])
        except subprocess.CalledProcessError as err:
            logger("Some recipes failed to execute: " + str(err))

    def cleanup(self):
        """
        Unmount and remove the remote repository if mounted during the script
        execution
        """
        logger("Cleaning up...")
        if self.remote_did_mount:
            logger("Attempting to unmount remote...", 1)
            subprocess.check_call([
                "umount",
                self.prefs["LocalMountPoint"]
            ])
        else:
            logger("Remote repository was not be mounted programmatically.", 1)

        if self.did_create_dir:
            logger("Removing temporary mount point...", 1)
            subprocess.check_call([
                "rmdir",
                self.prefs["LocalMountPoint"]
            ])
        else:
            logger("Temporary mount point was not created programatically.", 1)

    def initiate_run(self):
        """Execute the AutoPkg run"""
        conn_addr = self.prefs["SambaSettings"]["ConnectionAddress"]
        if self.is_server_available(conn_addr):
            self.prepare_remote(self.remote_addr)
            repo_ok = self.repo_integrity_check()

            if self.did_create_dir and self.remote_did_mount and repo_ok:
                if not AUTOPKG_DEBUG:
                    self.run_autopkg()
                else:
                    logger("AUTOPKG_DEBUG set to True, AutoPkg will not run")

                with open(self.report_location, 'rb') as report_plist:
                    report_data = plistlib.load(report_plist)
                    notify.generate_report(
                        report_data,
                        self.prefs,
                        self.send_pushover
                    )
        else:
            logger("Aborting operation, server unavailable.")


if __name__ == "__main__":
    runner_instance = AutoPkgRunner()
    runner_instance.initiate_run()
    del runner_instance
    gc.collect()
