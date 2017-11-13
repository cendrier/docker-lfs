#! /usr/bin/python

import fnmatch
import getpass
import optparse
import os
import re
import socket
import subprocess
import sys

#-----------------------------------------------------------------------

def get_current_branch():
    branch_list = os.popen("git branch", "r").readlines()
    for branch_line in branch_list:
        branch = branch_line.strip()
	if branch.startswith("* "):
	    return branch[2:]
    return "unknown branch"

#-----------------------------------------------------------------------

def get_all_branches():
    branches = [ ]
    branch_list = os.popen("git branch", "r").readlines()
    for branch_line in branch_list:
        branch = branch_line.strip()
	if branch.startswith("* "):
	    branches.append(branch[2:])
	else:
	    branches.append(branch)
    return branches

#-----------------------------------------------------------------------

def compute_tag(branch_name):
    dockerfile_contents = open("Dockerfile", "r").read()
    m = re.search("JENKINS_VERSION.*JENKINS_VERSION:-([0-9.]*)", dockerfile_contents)
    if m:
        return "markewaite/" + branch_name + ":" + m.group(1)
    return "markewaite/" + branch_name + ":latest"

#-----------------------------------------------------------------------

def is_home_network():
    if "hp-ux" in sys.platform:
        return False # No HP-UX on my home networks
    from socket import socket, SOCK_DGRAM, AF_INET
    s = socket(AF_INET, SOCK_DGRAM)
    s.settimeout(1.0)
    try:
        s.connect(("google.com", 0))
    except:
        return True
    return s.getsockname()[0].startswith("172")

#-----------------------------------------------------------------------

def get_fqdn():
    fqdn = socket.getfqdn()
    if not "." in fqdn:
        if is_home_network():
	    fqdn = fqdn + ".markwaite.net"
        else:
	    fqdn = fqdn + ".example.com"
    return fqdn

#-----------------------------------------------------------------------

# Fully qualified domain name of the host running this script
fqdn = get_fqdn()

#-----------------------------------------------------------------------

def replace_text_recursively(find, replace, include_pattern):
    print("Replacing '" + find + "' with '" + replace + "', in files matching '" + include_pattern + "'")
    # Thanks to https://stackoverflow.com/questions/4205854/python-way-to-recursively-find-and-replace-string-in-text-files
    for path, dirs, files in os.walk(os.path.abspath("ref")):
        for filename in fnmatch.filter(files, include_pattern):
            filepath = os.path.join(path, filename)
            with open(filepath) as f:
                s = f.read()
            s = s.replace(find, replace)
            with open(filepath, "w") as f:
                f.write(s)

#-----------------------------------------------------------------------

def replace_constants_in_ref():
    if not os.path.isdir("ref"):
        return
    replacements = { "localhost" : fqdn, "JENKINS_HOSTNAME" : fqdn, "LOGNAME" : getpass.getuser() }
    for find in replacements:
        replace_text_recursively(find, replacements[find], "*.xml")

#-----------------------------------------------------------------------

def undo_replace_constants_in_ref():
    if not os.path.isdir("ref"):
        return
    command = [ "git", "checkout", "--", "ref" ]
    subprocess.check_call(command)

#-----------------------------------------------------------------------

def build_one_image(branch_name):
    replace_constants_in_ref()
    tag = compute_tag(branch_name)
    print("Building " + tag)
    command = [ "docker", "build", "-t", tag, ".", ]
    subprocess.check_call(command)
    undo_replace_constants_in_ref()

#-----------------------------------------------------------------------

def get_predecessor_branch(current_branch, all_branches):
    last = "upstream/" + current_branch
    if current_branch == "lts":
        last = "upstream/master"
    if current_branch == "cjt":
        last = "cjt"
    for branch in all_branches:
        if branch == current_branch:
	    return last
        if current_branch.startswith(branch):
	    last = branch
    return last

#-----------------------------------------------------------------------

def merge_predecessor_branch(current_branch, all_branches):
    predecessor_branch = get_predecessor_branch(current_branch, all_branches)
    command = [ "git", "merge", "--no-edit", predecessor_branch ]
    print("Merging from " + predecessor_branch + " to " + current_branch)
    subprocess.check_call(command)

#-----------------------------------------------------------------------

def push_current_branch():
    command = [ "git", "push" ]
    print("Pushing current branch")
    subprocess.check_call(command)

#-----------------------------------------------------------------------

def checkout_branch(target_branch):
    subprocess.check_call(["git", "clean", "-xffd"])
    subprocess.check_call(["git", "reset", "--hard", "HEAD"])
    # lts-with-plugins and cjt-with-plugins contain large binaries
    if target_branch in ["lts-with-plugins", "cjt-with-plugins"]:
        subprocess.check_call(["git", "lfs", "fetch", "public", "public/" + target_branch])
    # cjt-with-plugins-add-credentials contains some large binaries
    if target_branch == "cjt-with-plugins-add-credentials":
        subprocess.check_call(["git", "lfs", "fetch", "private", "private/" + target_branch])
    subprocess.check_call(["git", "checkout", target_branch])
    subprocess.check_call(["git", "pull"])

#-----------------------------------------------------------------------

def docker_build(args = []):
    help_text = """%prog [options] [host(s)]
Build docker images.   Use -h for help."""
    parser = optparse.OptionParser(usage=help_text)

    # keep at optparse for 2.6. compatibility
    parser.add_option("-a", "--all", action="store_true", default=False, help="build all images")

    options, arg_hosts = parser.parse_args()

    original_branch = get_current_branch()
    all_branches = get_all_branches()

    if options.all:
        branches = all_branches
    else:
        branches = [ original_branch, ]

    for branch in branches:
        print("Building " + branch)
        checkout_branch(branch)
        merge_predecessor_branch(branch, all_branches)
        build_one_image(branch)
        push_current_branch()

    if original_branch != get_current_branch():
        checkout_branch(original_branch)

#-----------------------------------------------------------------------

if __name__ == "__main__": docker_build(sys.argv[1:])
