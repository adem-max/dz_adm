__version__ = "0.3.0"

# The oldest dz_core this hub works with: it reads dz_core's feature catalogue,
# sectors and tax regimes, and runs its setup on client sites. Raise it in the
# commit that starts using something new from dz_core.
DZ_CORE_MIN = "0.3.0"


def version_tuple(version):
	"""'0.12.1' -> (0, 12, 1), so versions compare as numbers."""
	return tuple(int(part) for part in str(version).split(".") if part.isdigit())


def check_dz_core():
	"""A bench whose dz_core is older than the hub expects fails here with a
	clear message, instead of an ImportError somewhere in the code."""
	import dz_core

	if version_tuple(dz_core.__version__) < version_tuple(DZ_CORE_MIN):
		raise ImportError(
			f"dz_hub {__version__} needs dz_core {DZ_CORE_MIN} or newer, "
			f"this bench has {dz_core.__version__}: update apps/dz_core, then bench migrate"
		)


check_dz_core()
