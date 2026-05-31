def test_imports() -> None:
    import localmind
    import localmind.app.cli
    import localmind.app.bootstrap
    import localmind.config.loader
    import localmind.config.schema
    import localmind.core.agent
    import localmind.core.context
    import localmind.core.lifecycle
    import localmind.core.session
    import localmind.llm.base
    import localmind.llm.manager
    import localmind.llm.openai_compatible
    import localmind.memory.sqlite
    import localmind.plugins
    import localmind.plugins.errors
    import localmind.plugins.manager
    import localmind.plugins.metadata
    import localmind.plugins.state
    import localmind.tools.base
    import localmind.tools.filesystem
    import localmind.tools.registry
    import localmind.utils.logging

    assert localmind.__version__ == "0.1.0"
