import gzip
import json
import os


class MockDistGitRepo:
    def __init__(self, pkg):
        self.pkg = pkg
        self._branches = None

    def _load(self):
        if self._branches is None:
            jsonfile = os.path.join(os.path.dirname(__file__),
                                    '../test-data/git',
                                    self.pkg + '.json.gz')
            with gzip.open(jsonfile, 'rt') as f:
                self._branches = json.load(f)

    def mirror(self, mirror_always=False):
        self._load()

    def get_branches(self, commit):
        self._load()

        if commit in self._branches:
            commit = self.rev_parse(commit)

        result = []
        for b in sorted(self._branches):
            if commit in self._branches[b]:
                result.append(b)

        if len(result) == 0:
            raise RuntimeError(f"{commit} not found on any branch")

        return result

    def rev_parse(self, ref):
        self._load()

        if ref in self._branches:
            return self._branches[ref][0]
        else:
            raise RuntimeError(f"Unknown ref {ref}")

    def order(self, commits):
        self._load()

        for b in sorted(self._branches):
            branch_commits = {v: k for k, v in enumerate(self._branches[b])}
            missing = False
            for c in commits:
                if c not in branch_commits:
                    missing = True
            if missing:
                continue
            return sorted(commits, key=lambda x: -branch_commits[x])

        raise RuntimeError(f"{commits} not all found on the same branch")


class MockDistGit:
    def __init__(self):
        pass

    def repo(self, pkg):
        return MockDistGitRepo(pkg)


def make_mock_distgit():
    return MockDistGit()
