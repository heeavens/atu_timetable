from bot.application import create_application


def main() -> None:
    application = create_application()
    application.run_polling()


if __name__ == "__main__":
    main()
