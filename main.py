import applog

# Before anything else, so an import-time or startup crash still lands in the
# log rather than disappearing behind the windowed build's missing console.
applog.setup()

from gui import App


def main():
    try:
        app = App()
        app.mainloop()
    except Exception:
        applog.log.critical("Fatal error at startup", exc_info=True)
        raise


if __name__ == "__main__":
    main()
