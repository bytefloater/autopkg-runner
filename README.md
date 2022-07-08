# AutoPkg Runner

### Features
* Support for SMB-hosted Munki Repositories
* Automatic Cleanup
* Generate and save remotely accessible HTML reports
* Support for Pushover Notifications

This automation script is designed to do the following:

1. Mount a specified SMB repository, if necessary.
2. Check for the presence of the repository folders.
3. Update all repos before run, if enabled. **[COMING SOON]**
4. Run all recipes in the recipe list.
5. Generate and save a report, also sending relevant notifications.


## Configuration

This script is configured by the file `script_settings.plist`.

### Structure

| Key                                       | Type       | Value                                                  |
|-------------------------------------------|------------|--------------------------------------------------------|
|                               AutoPkgPath | String     | Path to AutoPkg Executable                             |
|                                 CheckDirs | Array      | All directories contained in the Munki Repository Root |
|                           LocalMountPoint | String     | Path to the local mount point of the repository        |
|                          PushoverSettings | Dictionary | <span style="color: grey;">(2 items)</span>            |
|    &nbsp;&nbsp;&nbsp;&nbsp;ApplicationKey | String     | Pushover Application API Key                           |
|           &nbsp;&nbsp;&nbsp;&nbsp;UserKey | String     | Pushover User API Key                                  |
|                             SambaSettings | Dictionary | <span style="color: grey;">(4 items)</span>            |
| &nbsp;&nbsp;&nbsp;&nbsp;ConnectionAddress | String     | Zeroconf Connection Address                            |
|   &nbsp;&nbsp;&nbsp;&nbsp;CredentialsUser | String     | Username of Samba User                                 |
|   &nbsp;&nbsp;&nbsp;&nbsp;CredentialsPass | String     | Password of Samba User                                 |
|       &nbsp;&nbsp;&nbsp;&nbsp;ServerShare | String     | Name of Network Sharepoint                             |
|                            ScriptSettings | Dictionary | <span style="color: grey;">(2 items)</span>            |
|    &nbsp;&nbsp;&nbsp;&nbsp;RecipeListPath | String     | Path to RecipeList                                     |
|    &nbsp;&nbsp;&nbsp;&nbsp;ReportPlistDir | String     | Directory of the AutoPkg report save location          |
|     &nbsp;&nbsp;&nbsp;&nbsp;ReportBaseURL | String     | Report BaseURL (e.g. https://example.com/reports)      |


## Execution failed?

This script is designed to be executed from the same directory in which it is stored.

If the script fails to execute, run the following in a terminal
```
umount {local_mount_point}; rmdir {local_mount_point}
```
Changing `{local_mount_point}` for your mount point.