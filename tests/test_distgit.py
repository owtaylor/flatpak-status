import os
import shutil
import tempfile

from flatpak_status.distgit import DistGit, GitRepo


def create_source(source_dir):
    result = {}

    eog_dir = os.path.join(source_dir, 'rpms/eog')
    os.makedirs(eog_dir)

    repo = GitRepo(eog_dir)

    repo.do('init')
    repo.do('branch', '-m', 'main')
    repo.do('config', 'user.email', 'user@example.com')
    repo.do('config', 'user.name', 'Test User')

    with open(os.path.join(eog_dir, 'eog.spec'), 'w') as f:
        f.write('1\n')
    repo.do('add', 'eog.spec')
    repo.do('commit', '-m', 'Commit 1')

    result['Commit 1'] = repo.capture('rev-parse', 'HEAD')

    repo.do('branch', 'f29')

    with open(os.path.join(eog_dir, 'eog.spec'), 'w') as f:
        f.write('2\n')
    repo.do('commit', '-m', 'Commit 2', 'eog.spec')
    result['Commit 2'] = repo.capture('rev-parse', 'HEAD')

    return result


def test_distgit():
    try:
        source_dir = tempfile.mkdtemp()
        mirror_dir = tempfile.mkdtemp()

        commits = create_source(source_dir)

        distgit = DistGit(base_url='file://' + source_dir, mirror_dir=mirror_dir)
        repo = distgit.repo('rpms/eog')

        repo.mirror()

        head = repo.rev_parse('HEAD')
        assert head == commits['Commit 2']

        branches = repo.get_branches(commits['Commit 1'])
        assert set(branches) == set(['f29', 'main'])

        unordered = [commits[x] for x in ('Commit 2', 'Commit 1', 'Commit 2')]
        ordered = repo.order(unordered)
        assert ordered == [commits[x] for x in ('Commit 1', 'Commit 2', 'Commit 2')]

    finally:
        shutil.rmtree(source_dir)
        shutil.rmtree(mirror_dir)
