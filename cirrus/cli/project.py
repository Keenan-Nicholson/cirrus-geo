import os
import sys
import json
import yaml

from pathlib import Path

from cirrus.cli.constants import (
    DEFAULT_BUILD_DIR_NAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_SERVERLESS_FILENAME,
    SERVERLESS,
    SERVERLESS_PLUGINS,
)
from cirrus.cli.config import Config, DEFAULT_CONFIG_PATH
from cirrus.cli.exceptions import CirrusError
from cirrus.cli.utils import logging
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Project:
    def __init__(self, path: Path, config: Config=None) -> None:
        from cirrus.cli.collections import collections

        self._config = config
        self.collections = collections

        # set path, not _path, to use setter validation
        self._path = None
        self.path = path

    def __repr__(self):
        name = self.__class__.__name__
        return f'<{name}: {self.path}>'

    @property
    def path(self) -> Path:
        return self._path

    @property
    def path_safe(self) -> Path:
        return self._path

    @path.setter
    def path(self, path: Path) -> None:
        if path is not None and not self.dir_is_project(path):
            raise CirrusError(
                f"Cannot set project path, does not appear to be vaild project: '{p}'",
            )
        self._path = path
        self.collections.register_project(self)

    @property
    def config(self) -> Config:
        if self._config is None:
            if self.path is None:
                logger.warning(
                    f'Project path unset, cannot load configuration',
                )
            else:
                self._config = Config.from_project(self)
        return self._config

    @property
    def build_dir(self) -> Path:
        if self.path is None:
            return None
        return self.path.joinpath(DEFAULT_BUILD_DIR_NAME)

    @classmethod
    def resolve(cls, path: Path=None, strict=False):
        if path is None:
            path = Path(os.getcwd())
        else:
            path = path.resolve()

        project_path = None

        def dirs(path):
            yield path
            yield from path.parents

        for parent in dirs(path):
            if Project.dir_is_project(parent):
                project_path = parent
                break

        if strict and project_path is None:
            raise CirrusError("Unable to resolve project path and 'strict' resolution specified")

        return cls(project_path)

    @staticmethod
    def dir_is_project(path: Path) -> bool:
        config = path.joinpath(DEFAULT_CONFIG_FILENAME)
        return config.is_file()

    @classmethod
    def new(cls, path: Path) -> None:
        def maybe_write_file(name, content):
            f = path.joinpath(name)
            if f.exists():
                logger.info(f'{name} already exists, skipping')
            else:
                f.write_text(content)

        deps = SERVERLESS.copy()
        deps.update(SERVERLESS_PLUGINS)

        maybe_write_file(DEFAULT_CONFIG_FILENAME, DEFAULT_CONFIG_PATH.read_text())
        maybe_write_file('package.json', json.dumps(
            {
                'name': 'cirrus',
                'version': '0.0.0',
                'description': '',
                'devDependencies': deps,
            },
            indent=2,
        ))

        self = cls(path)

        for collection in self.collections.extendable_collections:
            self.path.joinpath(collection.user_dir_name).mkdir(exist_ok=True)

        return self

    def build(self) -> None:
        if self.path is None:
            raise CirrusError('Cannot build a project without the path set')

        import shutil
        from cirrus.cli.utils import misc

        # get our cirrus-lib version to inject in each lambda
        cirrus_req = [misc.get_cirrus_lib_requirement()]

        # make build dir or clean it up
        bd = self.build_dir
        try:
            bd.mkdir()
        except FileExistsError:
            pass

        # find existing lambda dirs, if any
        existing_dirs = set()
        for f in bd.iterdir():
            if not f.is_dir():
                continue
            if f.name == '.serverless':
                continue
            for d in f.iterdir():
                if not d.is_dir():
                    continue
                existing_dirs.add(d.resolve())

        # write serverless config
        self.config.to_file(bd.joinpath(DEFAULT_SERVERLESS_FILENAME))

        # setup all required lambda dirs
        fn_dirs = set()
        for collection in self.collections.lambda_collections:
            for fn in collection.values():
                outdir = fn.get_outdir(bd).resolve()
                if outdir in fn_dirs:
                    logger.debug(
                        f"Duplicate function name '{fn.name}': skipping",
                    )
                    continue

                fn_dirs.add(outdir)
                fn.link_to_outdir(outdir, cirrus_req)

        # clean up existing but no longer used lambda dirs
        for d in existing_dirs - fn_dirs:
            shutil.rmtree(d)

    def clean(self) -> None:
        if self.path is None:
            raise CirrusError('Cannot clean a project without the path set')

        import shutil
        bd = self.build_dir
        if not bd.is_dir():
            return
        for f in self.build_dir.iterdir():
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()
