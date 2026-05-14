"""python -m ig_summarize entrypoint (used by pipx console script)."""


def main() -> None:
    from ig_summarize.app import entrypoint

    entrypoint()


if __name__ == "__main__":
    main()
