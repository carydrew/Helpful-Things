#!/usr/bin/env python
#
# Cary Drew - August 2021 - Proof of Concept (little to no error checks)
#  - Does what I needed for work and I moved on (search for a user's folder in a folder that has about 150 users with similar VM names and query those VMs)
#  - took the base from cpaggen's getvnicinfo.py and adjusted it to work in my Django app, this version works via cmd line
#     - Made cpaggen's faster as it ignores a lot of the uneeded hosts/ESXi/VMs that I don't care about
#  - I made a few comments to help my error checking.
#
#  - There is error checking in my django version available on my github. But those are done via redirection.
#
# Known Errors: 
# - If a VM is powering up/down when checked it will cause an issue.
#
# Usage: Requires folder name for search and vcenter creds
# 


from __future__ import print_function
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from getpass import getpass
import atexit
import sys

def GetVMHosts(content):
    
    host_view = content.viewManager.CreateContainerView(content.rootFolder,
                                                        [vim.HostSystem],
                                                        True)
    # Added an if for 'esxi' because that's where my vms are hosted and I have others w/o that in name                                                   
    obj = [host for host in host_view.view if "esxi" in host.name]
    host_view.Destroy()
    return obj

def GetHostsPortgroups(hosts):
    
    hostPgDict = {}
    for host in hosts:
        pgs = host.config.network.portgroup
        hostPgDict[host] = pgs

    return hostPgDict


def PrintVmInfo(vm, ipAddy):
    connectionState = vm.runtime.connectionState
    vmPowerState = vm.runtime.powerState
    conn_power = vmPowerState + " - " + connectionState
    listIP, portGroup, vlanId = GetVMNics(vm, ipAddy)
    return conn_power, listIP, portGroup, vlanId


def GetVMNics(vm, ipAddy):
    i = 0
    for dev in vm.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualEthernetCard):
            dev_backing = dev.backing
            portGroup = None
            vlanId = None
            vSwitch = None
            if hasattr(dev_backing, 'port'):
                portGroupKey = dev.backing.port.portgroupKey
                dvsUuid = dev.backing.port.switchUuid
                try:
                    dvs = content.dvSwitchManager.QueryDvsByUuid(dvsUuid)
                    # This except causes a lot of issues, I pulled this with the basic function pre-edit so it's just commented out for now.
                    # It may get deleted later. 
                #except:
                #    portGroup = "** Error: DVS not found **"
                #    vlanId = "NA"
                #    vSwitch = "NA"
                finally:
                    pgObj = dvs.LookupDvPortGroup(portGroupKey)
                    portGroup = pgObj.config.name
                    vlanId = str(pgObj.config.defaultPortConfig.vlan.vlanId)
                    vSwitch = str(dvs.name)
            else:
                portGroup = dev.backing.network.name
                vmHost = vm.runtime.host
                # global variable hosts is a list, not a dict
                host_pos = hosts.index(vmHost)
                viewHost = hosts[host_pos]
                # global variable hostPgDict stores portgroups per host
                pgs = hostPgDict[viewHost]
                for p in pgs:
                    if portGroup in p.key:
                        vlanId = str(p.spec.vlanId)
                        vSwitch = str(p.spec.vswitchName)
            if portGroup is None:
                portGroup = 'NA'
            if vlanId is None:
                vlanId = 'NA'
            if vSwitch is None:
                vSwitch = 'NA'

            # Checking for machines that don't have vmware tools - can't pull the IP on those vms.
            if vm.guest.toolsRunningStatus != "guestToolsRunning" and vm.runtime.powerState == "poweredOn":
                thisIP = "VMware Tools is not installed on this VM."

            # This will cut out IPv6 IPs. Put all IPv4 IPs in a list, then make it a string. 
            elif vm.runtime.powerState == "poweredOn" :
                while i < len(ipAddy):
                    splitIP = str(ipAddy[i].ipAddress)
                    splitIP = splitIP[11:-1].split("'")
                    listIP = []
                    for ip in splitIP:
                        if '.' in ip:
                            listIP.append(ip)
                    thisIP = ", ".join(listIP)
                    i += 1
            
            # Checking for machines that are powered off - otherwise it throws an error for the IP
            elif vm.runtime.powerState != "poweredOn" :
                thisIP = ""

    return thisIP, portGroup, vlanId
            

def GetArgs():
    if len(sys.argv) != 4:

        # Host is your vcenter url
        host = "vcenter.domain.com"
        # Your vcenter creds
        Query_user = input('What is your username? ')
        password = getpass('What is your password? ')
    else:
        host, Query_user, password = sys.argv[1:]
    return host, Query_user, password

def User_Folder():
    global hosts, hostPgDict, content

    # The folder name you want to pull all VMs from, plus 1 more folder deep. 
    user_name = input('What is the folder you are looking for? ')
    host, Query_user, password = GetArgs()
    serviceInstance = SmartConnect(host=host,
                                   user=Query_user,
                                   pwd=password,
                                   port=443)
    atexit.register(Disconnect, serviceInstance)
    content = serviceInstance.RetrieveContent()
    hosts = GetVMHosts(content)
    hostPgDict = GetHostsPortgroups(hosts)
        # Getting the User specific folder and VMs
    obj = content.searchIndex.FindByInventoryPath("dc/vm/foo/bar")        
        # This will pull the specific requested users stuff
    for vm_folders in obj.childEntity:
        if vm_folders.name == user_name:
            userFolder = vm_folders
            return userFolder
    


def env_check(): # This is the main function

    # The answer list/dict is the what actually holds each item to return to the django template
    answer = []

    User_folder = User_Folder()

    if hasattr(User_folder, 'childEntity'):
        for vms in User_folder.childEntity:
            for UserItem in vms.childEntity:
                if hasattr(UserItem ,'childEntity'):
                    for vm in UserItem.childEntity:
                        ipAddy = vm.guest.net
                        conn_power, listIP, portGroup, vlanId = PrintVmInfo(vm, ipAddy)
                        answer.append({
                                        "name" : UserItem.name[7:] + " - " + vm.name,
                                        "power" : conn_power,
                                        "port": portGroup,
                                        "ip" : listIP,
                                        "vlan" : vlanId})
                else: 
                    ipAddy = UserItem.guest.net
                    conn_power, listIP, portGroup, vlanId = PrintVmInfo(UserItem, ipAddy)
                    answer.append({
                                    "name" : UserItem.name,
                                    "power" : conn_power,
                                    "port": portGroup,
                                    "ip" : listIP,
                                    "vlan" : vlanId})
                
        print(answer)

        #If you want to show the other possible folders to query, uncomment the next line
        #print(User_folder)


def vm_user_query():
    host, Query_user, password = GetArgs()
    serviceInstance = SmartConnect(host=host,
                                   user=Query_user,
                                   pwd=password,
                                   port=443)
    atexit.register(Disconnect, serviceInstance)
    content = serviceInstance.RetrieveContent()
    
    # Getting the User specific folder and VMs
    obj = content.searchIndex.FindByInventoryPath("dc/vm/foo/bar")
    
    # This will pull all the folders listed in vCenter so you know what is available to query
    vm_users = []
    for vm_folders in obj.childEntity:
        the_name = vm_folders.name
        vm_users.append(the_name)
    vm_users.sort()
    return vm_users

# Main section
if __name__ == "__main__":
    sys.exit(env_check())