#! /usr/bin/env python
"""Build a BMI implementation."""
from __future__ import print_function

import os
import sys
import types
import subprocess
import warnings

import yaml

from scripting.contexts import setenv, homebrew_hidden
from scripting.prompting import error, success

from .fetch import load_bmi_components
from .files import install_data_files
from .utils import cd, read_first_of
from .bocca import make_project, build_project, ProjectExistsError


_BUILD_FILES = ['.bmi.yaml', '.bmi.yml', os.path.join('.bmi', 'api.yaml'),
                os.path.join('.bmi', 'api.yml')]


def load_script(dir='.'):
    """Load a build script for an API description file.

    Parameters
    ----------
    dir : str, optional
        Path to folder that contains description file.

    Returns
    -------
    dict
        Build description

    Raises
    ------
    RuntimeError is the build is not a supported build type.
    """
    with cd(dir):
        (_, contents) = read_first_of(_BUILD_FILES)
    api = yaml.load(contents)

    if isinstance(api['build'], dict) and 'brew' in api['build']:
        return brew_install_instructions(api['build']['brew'])
    else:
        return bash_install_instructions(api['build'])


def brew_install_instructions(brewer):
    """Shell commands to install a formula with Homebrew.

    Parameters
    ----------
    brewer : dict
        Description of Homebrew formula.

    Returns
    -------
    list
        Shell commands needed to install the formula.
    """
    opts = brewer.get('options', [])
    formula = brewer['formula']

    if isinstance(opts, types.StringTypes):
        opts = [opts]

    return [' '.join(['brew', 'install', formula] + opts)]


def bash_install_instructions(script):
    """Shell commands to install something.

    Parameters
    ----------
    script : str or iterable
        Shell commands as a string or a list of strings.

    Returns
    -------
    list
        Shell commands.
    """
    if isinstance(script, types.StringTypes):
        return [script]
    else:
        return script


def render_output_block(output, indent=4):
    """Format a block of output text.

    Parameters
    ----------
    output : str
        Text to format.
    indent : int, optional
        Number of spaces to indent text.

    Returns
    -------
    str
        Formatted text.
    """
    lines = output.split(os.linesep)
    return os.linesep.join([' ' * indent + line for line in lines])


def execute_build(instructions, prefix='/usr/local'):
    """Build an API from a description.

    Parameters
    ----------
    build : dict
        Build description.
    """
    import pexpect

    os.environ['CSDMS_PREFIX'] = prefix

    child = pexpect.spawn('bash', echo=False)

    prompt = r"\[bmi-babel\]\$ "
    child.sendline(r"PS1='[bmi-babel]\$ '")
    child.expect([pexpect.TIMEOUT, prompt], timeout=10)

    for instruction in instructions:
        print('==> %s' % instruction, file=sys.stderr)
        child.sendline(instruction + ' || echo FAIL')
        i = child.expect([pexpect.TIMEOUT, prompt, 'FAIL'], timeout=300)
        print(render_output_block(child.before), file=sys.stderr)
        if i == 0 or i == 2:
            break


def babel_config(var):
    return subprocess.check_output(['babel-config', '--query-var={var}'.format(var=var)]).strip()


def find_java(env=None, hint=None):
    env = env or os.environ
    hint = hint or []
    if isinstance(hint, str):
        hint = [hint]

    search_paths = []
    if 'JAVA_HOME' in env:
        search_paths += [os.path.join(env['JAVA_HOME'], 'bin')]
    if hint:
        search_paths += [os.path.join(p, 'bin') for p in hint]
    if 'PATH' in env:
        search_paths += env['PATH'].split(os.pathsep)

    java_home = None
    for path in search_paths:
        path_to_java = os.path.join(path, 'java')
        if os.path.isfile(path_to_java):
            java_home = os.path.dirname(path)
            break

    return java_home


def setup_build_env(prefix):
    java_home = find_java(hint=babel_config('JAVAPREFIX'))

    build_env = {
        'PATH': os.pathsep.join(
            [os.path.join(sys.prefix, 'bin'),
             '/usr/bin', '/bin',
             '/usr/sbin', '/etc', '/usr/lib']),
        'CC': babel_config('CC'),
        'CXX': babel_config('CXX'),
        'USER': 'nobody',
        'PKG_CONFIG_PATH': os.path.join(sys.prefix, 'lib', 'pkgconfig'),
        'PREFIX': prefix,
    }

    if not java_home:
        warnings.warn('JAVA_HOME is not set.')
    else:
        build_env['PATH'] = os.pathsep.join([
            os.path.join(java_home, 'bin'),
            build_env['PATH']])

    return build_env


def babelize(path_to_bmi, prefix=None, build=True, install=True):
    """Babelize a BMI component.

    Parameters
    ----------
    path_to_bmi : str
        Path to BMI metadata folder.
    prefix : str, optional
        Path to installation base.
    build : bool, optional
        Create a bocca project and then build it.
    install : bool, optional
        Create, and build a bocca project and then install it.
    """
    prefix = prefix or os.path.join(os.sep, 'usr', 'local')
    build = build or install

    with homebrew_hidden():
        with setenv(setup_build_env(prefix), verbose=True):
            proj = load_bmi_components(path_to_bmi, install_prefix=prefix,
                                       build_api=False)

            try:
                build_dir = make_project(proj, clobber=True)
            except ProjectExistsError as error:
                error('Project exists: {dir}'.format(dir=path_to_bmi))
                return None

            if build:
                build_project(build_dir, prefix=prefix, install=install)
                success('created bocca project: {dir}'.format(dir=build_dir))

            if install:
                proj = load_bmi_components(path_to_bmi, install_prefix=prefix,
                                           build_api=False)
                for bmi in proj['bmi']:
                    install_data_files(bmi['path'], prefix,
                                       include_metadata=True)
                success('installed bocca project: {dir}'.format(dir=prefix))

    for dir in [os.path.abspath(d) for d in path_to_bmi]:
        success('babelized BMI project: {dir}'.format(dir=dir))


def execute_api_build(dir='.', prefix='/usr/local'):
    """Build an API from a file.

    Parameters
    ----------
    dir : str, optional
        Path to folder that contains description file.
    """
    execute_build(build.load_script(dir=dir), prefix=prefix)
