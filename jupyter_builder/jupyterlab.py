
import logging
from traitlets import Bool, HasTraits, Instance, Unicode, default


class AppOptions(HasTraits):
    """Options object for build system"""

    def __init__(self, logger=None, core_config=None, **kwargs):
        if core_config is not None:
            kwargs["core_config"] = core_config
        if logger is not None:
            kwargs["logger"] = logger

        # use the default if app_dir is empty
        if "app_dir" in kwargs and not kwargs["app_dir"]:
            kwargs.pop("app_dir")

        super().__init__(**kwargs)

    app_dir = Unicode(help="The application directory")

    use_sys_dir = Bool(
        True,
        help=("Whether to shadow the default app_dir if that is set to a non-default value"),
    )

    logger = Instance(logging.Logger, help="The logger to use")

    core_config = Instance(CoreConfig, help="Configuration for core data")

    kill_event = Instance(Event, args=(), help="Event for aborting call")

    labextensions_path = List(
        Unicode(), help="The paths to look in for prebuilt JupyterLab extensions"
    )

    registry = Unicode(help="NPM packages registry URL")

    splice_source = Bool(False, help="Splice source packages into app directory.")

    skip_full_build_check = Bool(
        False,
        help=(
            "If true, perform only a quick check that the lab build is up to date."
            " If false, perform a thorough check, which verifies extension contents."
        ),
    )

    @default("logger")
    def _default_logger(self):
        return logging.getLogger("jupyterlab")

    # These defaults need to be federated to pick up
    # any changes to env vars:
    @default("app_dir")
    def _default_app_dir(self):
        return get_app_dir()

    @default("core_config")
    def _default_core_config(self):
        return CoreConfig()

    @default("registry")
    def _default_registry(self):
        config = _yarn_config(self.logger)["yarn config"]
        return config.get("registry", YARN_DEFAULT_REGISTRY)

def _ensure_options(options):
    """Helper to use deprecated kwargs for AppOption"""
    if options is None:
        return AppOptions()
    elif issubclass(options.__class__, AppOptions):
        return options
    else:
        return AppOptions(**options)
    
def build(
    name=None,
    version=None,
    static_url=None,
    kill_event=None,
    clean_staging=False,
    app_options=None,
    production=True,
    minimize=True,
):
    """Build the JupyterLab application."""
    app_options = _ensure_options(app_options)
    _node_check(app_options.logger)
    handler = _AppHandler(app_options)
    return handler.build(
        name=name,
        version=version,
        static_url=static_url,
        production=production,
        minimize=minimize,
        clean_staging=clean_staging,
    )