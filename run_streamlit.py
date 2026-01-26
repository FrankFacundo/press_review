import sys as sts
import streamlit.web.cli as stcli
from importlib import resources


def main() -> None:
    app_path = resources.files("luxnews").joinpath("streamlit_app.py")
    sts.argv = ["streamlit", "run", str(app_path)]
    sts.exit(stcli.main())


if __name__ == "__main__":
    main()
