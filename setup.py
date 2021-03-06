import os
import re
import sys
import platform
import subprocess
import glob
import setuptools
import pathlib
from pkg_resources import Distribution, get_distribution
from setuptools import setup, Extension
from setuptools import Extension
from setuptools.command.build_ext import build_ext, copy_file
from distutils import log

from distutils.version import LooseVersion

MIN_SETUPTOOLS_VERSION = "31.0.0"
assert (LooseVersion(setuptools.__version__) >= LooseVersion(MIN_SETUPTOOLS_VERSION)), "LIEF requires a setuptools version '{}' or higher (pip install setuptools --upgrade)".format(MIN_SETUPTOOLS_VERSION)

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
PACKAGE_NAME = "lief"

class LiefDistribution(setuptools.Distribution):
    global_options = setuptools.Distribution.global_options + [
        ('lief-test', None, 'Build and make tests'),
        ('ninja', None, 'Use Ninja as build system'),
        ('sdk', None, 'Build SDK package'),
        ]

    def __init__(self, attrs=None):
        self.lief_test = False
        self.ninja     = False
        self.sdk       = False
        super().__init__(attrs)


class Module(Extension):
    def __init__(self, name, sourcedir='', *args, **kwargs):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(os.path.join(CURRENT_DIR))


class BuildLibrary(build_ext):
    def run(self):
        try:
            out = subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed to build the following extensions: " +
                               ", ".join(e.name for e in self.extensions))

        #if platform.system() == "Windows":
        #    cmake_version = LooseVersion(re.search(r'version\s*([\d.]+)', out.decode()).group(1))
        #    if cmake_version < '3.1.0':
        #        raise RuntimeError("CMake >= 3.1.0 is required on Windows")
        for ext in self.extensions:
            self.build_extension(ext)
        self.copy_extensions_to_source()

    @staticmethod
    def has_ninja():
        try:
            subprocess.check_call(['ninja', '--version'])
            return True
        except Exception as e:
            return False

    @staticmethod
    def sdk_suffix():
        if platform.system() == "Windows":
            return "zip"
        return "tar.gz"



    def build_extension(self, ext):
        if self.distribution.lief_test:
            log.info("LIEF tests enabled!")
        fullname = self.get_ext_fullname(ext.name)
        filename = self.get_ext_filename(fullname)

        jobs = self.parallel if self.parallel else 1


        source_dir                     = ext.sourcedir
        build_temp                     = self.build_temp
        extdir                         = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_library_output_directory = os.path.abspath(os.path.dirname(build_temp))
        cfg                            = 'Debug' if self.debug else 'Release'
        is64                           = sys.maxsize > 2**32

        cmake_args = [
            '-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={}'.format(cmake_library_output_directory),
            '-DPYTHON_EXECUTABLE={}'.format(sys.executable),
            '-DLIEF_PYTHON_API=on',
        ]

        if self.distribution.lief_test:
            cmake_args += ["-DLIEF_TESTS=on"]

        build_args = ['--config', cfg]

        if platform.system() == "Windows":
            cmake_args += [
                '-DCMAKE_BUILD_TYPE={}'.format(cfg),
                '-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), cmake_library_output_directory),
                '-DLIEF_USE_CRT_RELEASE=MT',
            ]
            cmake_args += ['-A', 'x64'] if is64 else []

            # Specific to appveyor
            #if os.getenv("APPVEYOR", False):
            #    build_args += ['--', '/v:m']
            #    logger = os.getenv("MSBuildLogger", None)
            #    if logger:
            #        build_args += ['/logger:{}'.format(logger)]
            #else:
            build_args += ['--', '/m']
        else:
            cmake_args += ['-DCMAKE_BUILD_TYPE={}'.format(cfg)]

        env = os.environ.copy()

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        build_with_ninja = False
        if self.has_ninja() and self.distribution.ninja:
            cmake_args += ["-G", "Ninja"]
            build_with_ninja = True


        # 1. Configure
        configure_cmd = ['cmake', ext.sourcedir] + cmake_args
        log.info(" ".join(configure_cmd))
        subprocess.check_call(configure_cmd, cwd=self.build_temp, env=env)

        # 2. Build
        targets = {
            'python_bindings': 'pyLIEF',
        }
        if self.distribution.sdk:
            targets['sdk'] = "package"

        if platform.system() == "Windows":
            build_cmd = ['cmake', '--build', '.', '--target', "lief_samples"] + build_args
            #log.info(" ".join(build_cmd))

            if self.distribution.lief_test:
                subprocess.check_call(['cmake', '--build', '.', '--target', "lief_samples"] + build_args, cwd=self.build_temp, env=env)
                subprocess.check_call(configure_cmd, cwd=self.build_temp, env=env)
                subprocess.check_call(['cmake', '--build', '.', '--target', "ALL_BUILD"] + build_args, cwd=self.build_temp, env=env)
                subprocess.check_call(['cmake', '--build', '.', '--target', "check-lief"] + build_args, cwd=self.build_temp, env=env)
            else:
                subprocess.check_call(['cmake', '--build', '.', '--target', targets['python_bindings']] + build_args, cwd=self.build_temp, env=env)

            if 'sdk' in targets:
                subprocess.check_call(['cmake', '--build', '.', '--target', targets['sdk']] + build_args, cwd=self.build_temp, env=env)

        else:
            if build_with_ninja:
                if self.distribution.lief_test:
                    subprocess.check_call(['ninja', "lief_samples"], cwd=self.build_temp)
                    subprocess.check_call(configure_cmd, cwd=self.build_temp)
                    subprocess.check_call(['ninja'], cwd=self.build_temp)
                    subprocess.check_call(['ninja', "check-lief"], cwd=self.build_temp)
                else:
                    subprocess.check_call(['ninja', targets['python_bindings']], cwd=self.build_temp)

                if 'sdk' in targets:
                    subprocess.check_call(['ninja', targets['sdk']], cwd=self.build_temp)
            else:
                log.info("Using {} jobs".format(jobs))
                if self.distribution.lief_test:
                    subprocess.check_call(['make', '-j', str(jobs), "lief_samples"], cwd=self.build_temp)
                    subprocess.check_call(configure_cmd, cwd=self.build_temp)
                    subprocess.check_call(['make', '-j', str(jobs), "all"], cwd=self.build_temp)
                    subprocess.check_call(['make', '-j', str(jobs), "check-lief"], cwd=self.build_temp)
                else:
                    subprocess.check_call(['make', '-j', str(jobs), targets['python_bindings']], cwd=self.build_temp)

                if 'sdk' in targets:
                    subprocess.check_call(['make', '-j', str(jobs), targets['sdk']], cwd=self.build_temp)
        pylief_dst  = os.path.join(self.build_lib, self.get_ext_filename(self.get_ext_fullname(ext.name)))


        libsuffix = pylief_dst.split(".")[-1]

        pylief_path = os.path.join(cmake_library_output_directory, "{}.{}".format(PACKAGE_NAME, libsuffix))
        if platform.system() == "Windows":
            pylief_path = os.path.join(cmake_library_output_directory, "Release", "api", "python", "Release", "{}.{}".format(PACKAGE_NAME, libsuffix))

        if not os.path.exists(self.build_lib):
            os.makedirs(self.build_lib)

        log.info("Copying {} into {}".format(pylief_path, pylief_dst))
        copy_file(
                pylief_path, pylief_dst, verbose=self.verbose,
                dry_run=self.dry_run)


        # SDK
        # ===
        if self.distribution.sdk:
            sdk_path = list(pathlib.Path(self.build_temp).rglob("LIEF-*.{}".format(self.sdk_suffix())))
            if len(sdk_path) == 0:
                log.error("Unable to find SDK archive")
                sys.exit(1)

            sdk_path = str(sdk_path.pop())
            sdk_output = str(pathlib.Path(CURRENT_DIR) / "build")

            copy_file(
                sdk_path, sdk_output, verbose=self.verbose,
                dry_run=self.dry_run)



# From setuptools-git-version
command       = 'git describe --tags --long --dirty'
is_tagged_cmd = 'git tag --list --points-at=HEAD'
fmt           = '{tag}.dev0'
fmt_tagged    = '{tag}'

def format_version(version, fmt=fmt):
    parts = version.split('-')
    assert len(parts) in (3, 4)
    dirty = len(parts) == 4
    tag, count, sha = parts[:3]
    if count == '0' and not dirty:
        return tag
    return fmt.format(tag=tag, gitsha=sha.lstrip('g'))


def get_git_version(is_tagged):
    git_version = subprocess.check_output(command.split()).decode('utf-8').strip()
    if is_tagged:
        return format_version(version=git_version, fmt=fmt_tagged)
    return format_version(version=git_version, fmt=fmt)

def check_if_tagged():
    output = subprocess.check_output(is_tagged_cmd.split()).decode('utf-8').strip()
    return output != ""

def get_pkg_info_version(pkg_info_file):
    dist_info = Distribution.from_filename(os.path.join(CURRENT_DIR, "{}.egg-info".format(PACKAGE_NAME)))
    pkg = get_distribution('lief')
    return pkg.version


def get_version():
    version   = "0.0.0"
    pkg_info  = os.path.join(CURRENT_DIR, "{}.egg-info".format(PACKAGE_NAME), "PKG-INFO")
    git_dir   = os.path.join(CURRENT_DIR, ".git")
    if os.path.isdir(git_dir):
        is_tagged = False
        try:
            is_tagged = check_if_tagged()
        except:
            is_tagged = False

        try:
            return get_git_version(is_tagged)
        except:
            pass

    if os.path.isfile(pkg_info):
        return get_pkg_info_version(pkg_info)



version = get_version()
cmdclass = {
    'build_ext': BuildLibrary,
}

setup(
    distclass=LiefDistribution,
    ext_modules=[Module(PACKAGE_NAME)],
    cmdclass=cmdclass,
    version=version
)
