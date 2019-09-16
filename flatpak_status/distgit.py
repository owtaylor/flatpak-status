import functools
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


class GitError(Exception):
    pass


class OrderingError(Exception):
    pass


class GitRepo:
    def __init__(self, repo_dir):
        self.repo_dir = repo_dir

    def do(self, *args):
        full_args = ['git']
        full_args += args
        try:
            subprocess.check_call(full_args, cwd=self.repo_dir)
        except subprocess.CalledProcessError as e:
            raise GitError(f"{self.repo_dir}: {e}") from e

    def capture(self, *args):
        full_args = ['git']
        full_args += args
        try:
            return subprocess.check_output(full_args, cwd=self.repo_dir, encoding='UTF-8').strip()
        except subprocess.CalledProcessError as e:
            raise GitError(f"{self.repo_dir}: {e}") from e


class DistGitRepo(GitRepo):
    def __init__(self, pkg, repo_dir, origin, mirror_existing=True):
        super().__init__(repo_dir)
        self.pkg = pkg
        self.origin = origin
        self.mirror_existing = mirror_existing

    def exists(self):
        return os.path.exists(self.repo_dir)

    def mirror(self, mirror_always=False):
        if not self.exists():
            parent_dir = os.path.dirname(self.repo_dir)
            if not os.path.isdir(parent_dir):
                os.makedirs(parent_dir)
            subprocess.check_call(['git', 'clone', '--mirror', self.origin],
                                  cwd=parent_dir)
        else:
            if self.mirror_existing or mirror_always:
                logger.info("Refreshing existing mirror %s", self.pkg)
                self.do('remote', 'update')

    def _get_branches(self, commit, try_mirroring=False):
        return self.capture('branch',
                            '--contains', commit,
                            '--format=%(refname:lstrip=2)').split('\n')

    def get_branches(self, commit, try_mirroring=False):
        need_retry = False
        try:
            return self._get_branches(commit)
        except GitError:
            if try_mirroring:
                logger.warning(f"Couldn't find {commit} in {self.repo_dir}, refreshing mirror")
                need_retry = True
            else:
                raise

        if need_retry:
            self.mirror(mirror_always=True)
            return self._get_branches(commit)

    def rev_parse(self, ref):
        return self.capture('rev-parse', ref)

    def verify_rev(self, rev):
        try:
            self.capture('rev-parse', '--quiet', '--verify', rev)
            return True
        except subprocess.CalledProcessError:
            return False

    def order(self, commits):
        def compare(a, b):
            if a == b:
                return 0

            base = self.capture('merge-base', a, b)
            if base == a:
                return -1
            elif base == b:
                return 1
            else:
                raise OrderingError(f"Commits {a} and {b} are not comparable")

        return sorted(commits, key=functools.cmp_to_key(compare))


class DistGit:
    def __init__(self, base_url, mirror_dir, mirror_existing=True):
        self.base_url = base_url
        self.mirror_dir = mirror_dir
        self.mirror_existing = mirror_existing

    def repo(self, pkg):
        return DistGitRepo(pkg,
                           repo_dir=os.path.join(self.mirror_dir, pkg + '.git'),
                           origin=self.base_url + '/' + pkg,
                           mirror_existing=self.mirror_existing)

    def mirror_all(self):
        for f in sorted(os.listdir(self.mirror_dir)):
            for g in sorted(os.listdir(os.path.join(self.mirror_dir, f))):
                if g.endswith('.git'):
                    self.repo(os.path.join(f, g[:-4])).mirror(mirror_always=True)
