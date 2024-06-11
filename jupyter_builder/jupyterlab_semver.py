# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# This file comes from https://github.com/podhmo/python-semver/blob/b42e9896e391e086b773fc621b23fa299d16b874/semver/__init__.py
#
# It is licensed under the following license:
#
# MIT License

# Copyright (c) 2016 podhmo

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


def semver(version, loose):
    if isinstance(version, SemVer):
        if version.loose == loose:
            return version
        else:
            version = version.version
    elif not isinstance(version, string_type):  # xxx:
        raise ValueError(f"Invalid Version: {version}")

    """
    if (!(this instanceof SemVer))
       return new SemVer(version, loose);
    """
    return SemVer(version, loose)


make_semver = semver


class SemVer:
    def __init__(self, version, loose):
        logger.debug("SemVer %s, %s", version, loose)
        self.loose = loose
        self.raw = version

        m = regexp[LOOSE if loose else FULL].search(version.strip())
        if not m:
            if not loose:
                raise ValueError(f"Invalid Version: {version}")
            m = regexp[RECOVERYVERSIONNAME].search(version.strip())
            self.major = int(m.group(1)) if m.group(1) else 0
            self.minor = int(m.group(2)) if m.group(2) else 0
            self.patch = 0
            if not m.group(3):
                self.prerelease = []
            else:
                self.prerelease = [
                    (int(id) if NUMERIC.search(id) else id) for id in m.group(3).split(".")
                ]
        else:
            #  these are actually numbers
            self.major = int(m.group(1))
            self.minor = int(m.group(2))
            self.patch = int(m.group(3))
            #  numberify any prerelease numeric ids
            if not m.group(4):
                self.prerelease = []
            else:
                self.prerelease = [
                    (int(id) if NUMERIC.search(id) else id) for id in m.group(4).split(".")
                ]
            if m.group(5):
                self.build = m.group(5).split(".")
            else:
                self.build = []

        self.format()  # xxx:

    def format(self):
        self.version = f"{self.major}.{self.minor}.{self.patch}"
        if len(self.prerelease) > 0:
            self.version += "-{}".format(".".join(str(v) for v in self.prerelease))
        return self.version

    def __repr__(self):
        return f"<SemVer {self} >"

    def __str__(self):
        return self.version

    def compare(self, other):
        logger.debug("SemVer.compare %s %s %s", self.version, self.loose, other)
        if not isinstance(other, SemVer):
            other = make_semver(other, self.loose)
        result = self.compare_main(other) or self.compare_pre(other)
        logger.debug("compare result %s", result)
        return result

    def compare_main(self, other):
        if not isinstance(other, SemVer):
            other = make_semver(other, self.loose)

        return (
            compare_identifiers(str(self.major), str(other.major))
            or compare_identifiers(str(self.minor), str(other.minor))
            or compare_identifiers(str(self.patch), str(other.patch))
        )

    def compare_pre(self, other):
        if not isinstance(other, SemVer):
            other = make_semver(other, self.loose)

        #  NOT having a prerelease is > having one
        is_self_more_than_zero = len(self.prerelease) > 0
        is_other_more_than_zero = len(other.prerelease) > 0

        if not is_self_more_than_zero and is_other_more_than_zero:
            return 1
        elif is_self_more_than_zero and not is_other_more_than_zero:
            return -1
        elif not is_self_more_than_zero and not is_other_more_than_zero:
            return 0

        i = 0
        while True:
            a = list_get(self.prerelease, i)
            b = list_get(other.prerelease, i)
            logger.debug("prerelease compare %s: %s %s", i, a, b)
            i += 1
            if a is None and b is None:
                return 0
            elif b is None:
                return 1
            elif a is None:
                return -1
            elif a == b:
                continue
            else:
                return compare_identifiers(str(a), str(b))

    def inc(self, release, identifier=None):
        logger.debug("inc release %s %s", self.prerelease, release)
        if release == "premajor":
            self.prerelease = []
            self.patch = 0
            self.minor = 0
            self.major += 1
            self.inc("pre", identifier=identifier)
        elif release == "preminor":
            self.prerelease = []
            self.patch = 0
            self.minor += 1
            self.inc("pre", identifier=identifier)
        elif release == "prepatch":
            # If this is already a prerelease, it will bump to the next version
            # drop any prereleases that might already exist, since they are not
            # relevant at this point.
            self.prerelease = []
            self.inc("patch", identifier=identifier)
            self.inc("pre", identifier=identifier)
        elif release == "prerelease":
            # If the input is a non-prerelease version, this acts the same as
            # prepatch.
            if len(self.prerelease) == 0:
                self.inc("patch", identifier=identifier)
            self.inc("pre", identifier=identifier)
        elif release == "major":
            # If this is a pre-major version, bump up to the same major version.
            # Otherwise increment major.
            # 1.0.0-5 bumps to 1.0.0
            # 1.1.0 bumps to 2.0.0
            if self.minor != 0 or self.patch != 0 or len(self.prerelease) == 0:
                self.major += 1
            self.minor = 0
            self.patch = 0
            self.prerelease = []
        elif release == "minor":
            # If this is a pre-minor version, bump up to the same minor version.
            # Otherwise increment minor.
            # 1.2.0-5 bumps to 1.2.0
            # 1.2.1 bumps to 1.3.0
            if self.patch != 0 or len(self.prerelease) == 0:
                self.minor += 1
            self.patch = 0
            self.prerelease = []
        elif release == "patch":
            #  If this is not a pre-release version, it will increment the patch.
            #  If it is a pre-release it will bump up to the same patch version.
            #  1.2.0-5 patches to 1.2.0
            #  1.2.0 patches to 1.2.1
            if len(self.prerelease) == 0:
                self.patch += 1
            self.prerelease = []
        elif release == "pre":
            #  This probably shouldn't be used publicly.
            #  1.0.0 "pre" would become 1.0.0-0 which is the wrong direction.
            logger.debug("inc prerelease %s", self.prerelease)
            if len(self.prerelease) == 0:
                self.prerelease = [0]
            else:
                i = len(self.prerelease) - 1
                while i >= 0:
                    if isinstance(self.prerelease[i], int):
                        self.prerelease[i] += 1
                        i -= 2
                    i -= 1
                # ## this is needless code in python ##
                # if i == -1:  # didn't increment anything
                #     self.prerelease.append(0)
            if identifier is not None:
                # 1.2.0-beta.1 bumps to 1.2.0-beta.2,
                # 1.2.0-beta.fooblz or 1.2.0-beta bumps to 1.2.0-beta.0
                if self.prerelease[0] == identifier:
                    if not isinstance(self.prerelease[1], int):
                        self.prerelease = [identifier, 0]
                else:
                    self.prerelease = [identifier, 0]
        else:
            raise ValueError(f"invalid increment argument: {release}")
        self.format()
        self.raw = self.version
        return self


def compare(a, b, loose):
    return make_semver(a, loose).compare(b)


def gt(a, b, loose):
    return compare(a, b, loose) > 0


def lt(a, b, loose):
    return compare(a, b, loose) < 0


def gte(a, b, loose):
    return compare(a, b, loose) >= 0


def lte(a, b, loose):
    return compare(a, b, loose) <= 0
