""" Build index from directory listing
From: https://stackoverflow.com/questions/39048654/how-to-enable-directory-indexing-on-github-pages

make_index.py </path/to/directory>
"""

INDEX_TEMPLATE = r"""
<html>
<title>Links for lief</title>
<body>
<h1>Links for lief</h1>
% for name in names:
    <a href="${base_url}/${name}">${name}</a><br />
% endfor
</body>
</html>
"""

EXCLUDED = ['index.html', '.gitkeep']
BASE_URL = "https://lief-project.github.io/packages/lief"

import os
import argparse

# May need to do "pip install mako"
from mako.template import Template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    fnames = [fname for fname in sorted(os.listdir(args.directory))
              if fname not in EXCLUDED]
    print(Template(INDEX_TEMPLATE).render(names=fnames, base_url=BASE_URL))


if __name__ == '__main__':
    main()
