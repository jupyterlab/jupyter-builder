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

import logging
import re

logger = logging.getLogger(__name__)

SEMVER_SPEC_VERSION = "2.0.0"

string_type = str


class _R:
    def __init__(self, i):
        self.i = i

    def __call__(self):
        v = self.i
        self.i += 1
        return v

    def value(self):
        return self.i


class Extendlist(list):
    def __setitem__(self, i, v):
        try:
            list.__setitem__(self, i, v)
        except IndexError:
            if len(self) == i:
                self.append(v)
            else:
                raise


def list_get(xs, i):
    try:
        return xs[i]
    except IndexError:
        return None


R = _R(0)
src = Extendlist()
regexp = {}

# The following Regular Expressions can be used for tokenizing,
# validating, and parsing SemVer version strings.

# ## Numeric Identifier
# A single `0`, or a non-zero digit followed by zero or more digits.

NUMERICIDENTIFIER = R()
src[NUMERICIDENTIFIER] = "0|[1-9]\\d*"

NUMERICIDENTIFIERLOOSE = R()
src[NUMERICIDENTIFIERLOOSE] = "[0-9]+"


# ## Non-numeric Identifier
# Zero or more digits, followed by a letter or hyphen, and then zero or
# more letters, digits, or hyphens.

NONNUMERICIDENTIFIER = R()
src[NONNUMERICIDENTIFIER] = "\\d*[a-zA-Z-][a-zA-Z0-9-]*"

# ## Main Version
# Three dot-separated numeric identifiers.

MAINVERSION = R()
src[MAINVERSION] = (
    "("
    + src[NUMERICIDENTIFIER]
    + ")\\."
    + "("
    + src[NUMERICIDENTIFIER]
    + ")\\."
    + "("
    + src[NUMERICIDENTIFIER]
    + ")"
)

MAINVERSIONLOOSE = R()
src[MAINVERSIONLOOSE] = (
    "("
    + src[NUMERICIDENTIFIERLOOSE]
    + ")\\."
    + "("
    + src[NUMERICIDENTIFIERLOOSE]
    + ")\\."
    + "("
    + src[NUMERICIDENTIFIERLOOSE]
    + ")"
)


# ## Pre-release Version Identifier
# A numeric identifier, or a non-numeric identifier.

PRERELEASEIDENTIFIER = R()
src[PRERELEASEIDENTIFIER] = "(?:" + src[NUMERICIDENTIFIER] + "|" + src[NONNUMERICIDENTIFIER] + ")"

PRERELEASEIDENTIFIERLOOSE = R()
src[PRERELEASEIDENTIFIERLOOSE] = (
    "(?:" + src[NUMERICIDENTIFIERLOOSE] + "|" + src[NONNUMERICIDENTIFIER] + ")"
)


# ## Pre-release Version
# Hyphen, followed by one or more dot-separated pre-release version
# identifiers.

PRERELEASE = R()
src[PRERELEASE] = (
    "(?:-(" + src[PRERELEASEIDENTIFIER] + "(?:\\." + src[PRERELEASEIDENTIFIER] + ")*))"
)

PRERELEASELOOSE = R()
src[PRERELEASELOOSE] = (
    "(?:-?(" + src[PRERELEASEIDENTIFIERLOOSE] + "(?:\\." + src[PRERELEASEIDENTIFIERLOOSE] + ")*))"
)

# ## Build Metadata Identifier
# Any combination of digits, letters, or hyphens.

BUILDIDENTIFIER = R()
src[BUILDIDENTIFIER] = "[0-9A-Za-z-]+"

# ## Build Metadata
# Plus sign, followed by one or more period-separated build metadata
# identifiers.

BUILD = R()
src[BUILD] = "(?:\\+(" + src[BUILDIDENTIFIER] + "(?:\\." + src[BUILDIDENTIFIER] + ")*))"

#  ## Full Version String
#  A main version, followed optionally by a pre-release version and
#  build metadata.

#  Note that the only major, minor, patch, and pre-release sections of
#  the version string are capturing groups.  The build metadata is not a
#  capturing group, because it should not ever be used in version
#  comparison.

FULL = R()
FULLPLAIN = "v?" + src[MAINVERSION] + src[PRERELEASE] + "?" + src[BUILD] + "?"

src[FULL] = "^" + FULLPLAIN + "$"

#  like full, but allows v1.2.3 and =1.2.3, which people do sometimes.
#  also, 1.0.0alpha1 (prerelease without the hyphen) which is pretty
#  common in the npm registry.
LOOSEPLAIN = "[v=\\s]*" + src[MAINVERSIONLOOSE] + src[PRERELEASELOOSE] + "?" + src[BUILD] + "?"

LOOSE = R()
src[LOOSE] = "^" + LOOSEPLAIN + "$"

GTLT = R()
src[GTLT] = "((?:<|>)?=?)"

#  Something like "2.*" or "1.2.x".
#  Note that "x.x" is a valid xRange identifier, meaning "any version"
#  Only the first item is strictly required.
XRANGEIDENTIFIERLOOSE = R()
src[XRANGEIDENTIFIERLOOSE] = src[NUMERICIDENTIFIERLOOSE] + "|x|X|\\*"
XRANGEIDENTIFIER = R()
src[XRANGEIDENTIFIER] = src[NUMERICIDENTIFIER] + "|x|X|\\*"

XRANGEPLAIN = R()
src[XRANGEPLAIN] = (
    "[v=\\s]*("
    + src[XRANGEIDENTIFIER]
    + ")"
    + "(?:\\.("
    + src[XRANGEIDENTIFIER]
    + ")"
    + "(?:\\.("
    + src[XRANGEIDENTIFIER]
    + ")"
    + "(?:"
    + src[PRERELEASE]
    + ")?"
    + src[BUILD]
    + "?"
    + ")?)?"
)

XRANGEPLAINLOOSE = R()
src[XRANGEPLAINLOOSE] = (
    "[v=\\s]*("
    + src[XRANGEIDENTIFIERLOOSE]
    + ")"
    + "(?:\\.("
    + src[XRANGEIDENTIFIERLOOSE]
    + ")"
    + "(?:\\.("
    + src[XRANGEIDENTIFIERLOOSE]
    + ")"
    + "(?:"
    + src[PRERELEASELOOSE]
    + ")?"
    + src[BUILD]
    + "?"
    + ")?)?"
)

XRANGE = R()
src[XRANGE] = "^" + src[GTLT] + "\\s*" + src[XRANGEPLAIN] + "$"
XRANGELOOSE = R()
src[XRANGELOOSE] = "^" + src[GTLT] + "\\s*" + src[XRANGEPLAINLOOSE] + "$"

#  Tilde ranges.
#  Meaning is "reasonably at or greater than"
LONETILDE = R()
src[LONETILDE] = "(?:~>?)"

TILDETRIM = R()
src[TILDETRIM] = "(\\s*)" + src[LONETILDE] + "\\s+"
regexp[TILDETRIM] = re.compile(src[TILDETRIM], re.M)
tildeTrimReplace = r"\1~"

TILDE = R()
src[TILDE] = "^" + src[LONETILDE] + src[XRANGEPLAIN] + "$"
TILDELOOSE = R()
src[TILDELOOSE] = "^" + src[LONETILDE] + src[XRANGEPLAINLOOSE] + "$"

#  Caret ranges.
#  Meaning is "at least and backwards compatible with"
LONECARET = R()
src[LONECARET] = "(?:\\^)"

CARETTRIM = R()
src[CARETTRIM] = "(\\s*)" + src[LONECARET] + "\\s+"
regexp[CARETTRIM] = re.compile(src[CARETTRIM], re.M)
caretTrimReplace = r"\1^"

CARET = R()
src[CARET] = "^" + src[LONECARET] + src[XRANGEPLAIN] + "$"
CARETLOOSE = R()
src[CARETLOOSE] = "^" + src[LONECARET] + src[XRANGEPLAINLOOSE] + "$"

#  A simple gt/lt/eq thing, or just "" to indicate "any version"
COMPARATORLOOSE = R()
src[COMPARATORLOOSE] = "^" + src[GTLT] + "\\s*(" + LOOSEPLAIN + ")$|^$"
COMPARATOR = R()
src[COMPARATOR] = "^" + src[GTLT] + "\\s*(" + FULLPLAIN + ")$|^$"


#  An expression to strip any whitespace between the gtlt and the thing
#  it modifies, so that `> 1.2.3` ==> `>1.2.3`
COMPARATORTRIM = R()
src[COMPARATORTRIM] = "(\\s*)" + src[GTLT] + "\\s*(" + LOOSEPLAIN + "|" + src[XRANGEPLAIN] + ")"

#  this one has to use the /g flag
regexp[COMPARATORTRIM] = re.compile(src[COMPARATORTRIM], re.M)
comparatorTrimReplace = r"\1\2\3"


#  Something like `1.2.3 - 1.2.4`
#  Note that these all use the loose form, because they'll be
#  checked against either the strict or loose comparator form
#  later.
HYPHENRANGE = R()
src[HYPHENRANGE] = (
    "^\\s*(" + src[XRANGEPLAIN] + ")" + "\\s+-\\s+" + "(" + src[XRANGEPLAIN] + ")" + "\\s*$"
)

HYPHENRANGELOOSE = R()
src[HYPHENRANGELOOSE] = (
    "^\\s*("
    + src[XRANGEPLAINLOOSE]
    + ")"
    + "\\s+-\\s+"
    + "("
    + src[XRANGEPLAINLOOSE]
    + ")"
    + "\\s*$"
)

#  Star ranges basically just allow anything at all.
STAR = R()
src[STAR] = "(<|>)?=?\\s*\\*"

# version name recovery for convenient
RECOVERYVERSIONNAME = R()
_n = src[NUMERICIDENTIFIER]
_pre = src[PRERELEASELOOSE]
src[RECOVERYVERSIONNAME] = f"v?({_n})(?:\\.({_n}))?{_pre}?"

#  Compile to actual regexp objects.
#  All are flag-free, unless they were created above with a flag.
for i in range(R.value()):
    logger.debug("genregxp %s %s", i, src[i])
    if i not in regexp:
        regexp[i] = re.compile(src[i])


def parse(version, loose):
    r = regexp[LOOSE] if loose else regexp[FULL]
    m = r.search(version)
    if m:
        return semver(version, loose)
    else:
        return None


def valid(version, loose):
    v = parse(version, loose)
    if v.version:
        return v
    else:
        return None


def clean(version, loose):
    s = parse(version, loose)
    if s:
        return s.version
    else:
        return None


NUMERIC = re.compile(r"^\d+$")


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
                    (int(id_) if NUMERIC.search(id_) else id_) for id_ in m.group(3).split(".")
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
                    (int(id_) if NUMERIC.search(id_) else id_) for id_ in m.group(4).split(".")
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

    def compare_pre(self, other):  # noqa PLR0911
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
            msg = f"invalid increment argument: {release}"
            raise ValueError(msg)
        self.format()
        self.raw = self.version
        return self


def inc(version, release, loose, identifier=None):  # wow!
    try:
        return make_semver(version, loose).inc(release, identifier=identifier).version
    except Exception as e:
        logger.debug(e, exc_info=5)
        return None


def compare_identifiers(a, b):
    anum = NUMERIC.search(a)
    bnum = NUMERIC.search(b)

    if anum and bnum:
        a = int(a)
        b = int(b)

    if anum and not bnum:
        return -1
    elif bnum and not anum:
        return 1
    elif a < b:
        return -1
    elif a > b:
        return 1
    else:
        return 0


def rcompare_identifiers(a, b):
    return compare_identifiers(b, a)


def compare(a, b, loose):
    return make_semver(a, loose).compare(b)


def compare_loose(a, b):
    return compare(a, b, True)


def rcompare(a, b, loose):
    return compare(b, a, loose)


def make_key_function(loose):
    def key_function(version):
        v = make_semver(version, loose)
        key = (v.major, v.minor, v.patch)
        if v.prerelease:  # noqa SIM108
            key = key + tuple(v.prerelease)
        else:
            #  NOT having a prerelease is > having one
            key = (*key, float("inf"))

        return key

    return key_function


loose_key_function = make_key_function(True)
full_key_function = make_key_function(True)


def sort(list_, loose):
    keyf = loose_key_function if loose else full_key_function
    list_.sort(key=keyf)
    return list_


def rsort(list_, loose):
    keyf = loose_key_function if loose else full_key_function
    list_.sort(key=keyf, reverse=True)
    return list_


def gt(a, b, loose):
    return compare(a, b, loose) > 0


def lt(a, b, loose):
    return compare(a, b, loose) < 0


def gte(a, b, loose):
    return compare(a, b, loose) >= 0


def lte(a, b, loose):
    return compare(a, b, loose) <= 0
