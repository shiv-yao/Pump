if cmd == "help":
    return {
        "success": True,
        "output": (
            "/help\n"
            "/skills\n"
            "/providers\n"
            "/store\n"
            "/install <name> <url>\n"
            "/enable <name>\n"
            "/disable <name>\n"
            "/remove <name>\n"
            "/price <symbol>\n"
            "/signal <symbol>\n"
            "/scan <symbol1> [symbol2]\n"
            "/balance\n"
            "/positions\n"
            "/orders\n"
            "/buy <symbol> <amount>\n"
            "/sell <symbol> <amount>\n"
            "/killswitch\n"
            "/start_arb_bot\n"
            "/stop_arb_bot\n"
            "/arb_status\n"
            "/clear"
        )
    }
