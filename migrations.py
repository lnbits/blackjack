# the migration file is where you build your database tables
# If you create a new release for your extension ,
# remember the migration file is like a blockchain, never edit only add!

empty_dict: dict[str, str] = {}


async def m001_extension_settings(db):
    """
    Initial settings table.
    """

    await db.execute(
        f"""
        CREATE TABLE blackjack.extension_settings (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            risk_multiplier INT,
            rake FLOAT,
            rake_wallet_id TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )

    await db.execute(
        f"""
        CREATE TABLE blackjack.dealers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            wallet_id TEXT NOT NULL,
            min_bet INT NOT NULL,
            max_bet INT NOT NULL,
            decks INT NOT NULL,
            hit_soft_17 BOOLEAN NOT NULL,
            blackjack_payout TEXT NOT NULL,
            active BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )

    await db.execute(
        f"""
        CREATE TABLE blackjack.hands_played (
            id TEXT PRIMARY KEY,
            dealers_id TEXT NOT NULL,
            status TEXT,
            bet_amount INT,
            lnaddress TEXT,
            payment_hash TEXT,
            player_hand TEXT,
            dealer_hand TEXT,
            player_score INT,
            dealer_score INT,
            shoe TEXT,
            outcome TEXT,
            payout_amount INT,
            client_seed TEXT,
            server_seed TEXT,
            server_seed_hash TEXT,
            ended_at TIMESTAMP,
            paid BOOLEAN,
            payout_sent BOOLEAN,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )
