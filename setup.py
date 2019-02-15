from setuptools import setup

setup(name='flatpak-status',
      version='0.1',
      description='Status page for Fedora Flatpaks',
      url='https://pagure.io/otaylor/flatpak-status',
      author='Owen Taylor',
      author_email='otaylor@redhat.com',
      license='MIT',
      packages=['flatpak_status'],
      include_package_data=True,
      entry_points= {
          'console_scripts': [
              'flatpak-status=flatpak_status.cli:cli',
          ],
      })
