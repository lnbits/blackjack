window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  data() {
    return {
      dealersId: null,
      betAmount: null,
      minBet: minBet,
      maxBet: maxBet,
      lnAddress: 'test@fitting-sole-wildly.ngrok-free.app',
      gameStatus: 'waiting_for_bet', // waiting_for_bet, bet_placed, game_over
      gameStarted: false,
      gameFinished: false,
      dealerRevealed: false,
      resultMessage: '',
      resultColor: '',
      paymentRequest: '',
      paymentHash: '',
      showLnAddressDialog: false,
      showPaymentDialog: false,
      currentHandsPlayedId: null,
      gameHistory: [],
      gameState: {
        id: null,
        dealers_id: null,
        status: null,
        bet_amount: null,
        player_hand: [],
        dealer_hand: [],
        player_score: 0,
        dealer_score: 0,
        dealer_hidden_score: 0,
        outcome: null,
        payout_amount: 0,
        payout_sent: false,
        server_seed_hash: null,
        client_seed: null,
        server_seed: null,
        created_at: null,
        updated_at: null,
        ended_at: null,
        paid: false
      }
    }
  },
  methods: {
    placeBet() {
      if (!this.betAmount || this.betAmount <= 0) {
        Quasar.Notify.create({
          type: 'negative',
          message: 'Please enter a valid bet amount.'
        })
        return
      }
      if (!this.lnAddress) {
        Quasar.Notify.create({
          type: 'warning',
          message: 'LN Address is required for potential payout.'
        })
        return
      }
      this.submitBet()
    },

    async submitBet() {
      if (!this.lnAddress) {
        Quasar.Notify.create({
          type: 'warning',
          message: 'LN Address is required for potential payout.'
        })
        return
      }

      try {
        const requestData = {
          dealers_id: this.dealersId,
          bet_amount: parseInt(this.betAmount),
          lnaddress: this.lnAddress
          // client_seed will be set to payment hash after payment confirmation
        }

        const {data} = await LNbits.api.request(
          'POST',
          `/blackjack/api/v1/hands_played/${this.dealersId}`,
          null,
          requestData
        )

        this.currentHandsPlayedId = data.hands_played_id
        this.paymentHash = data.payment_hash
        this.paymentRequest = data.payment_request

        this.showLnAddressDialog = false
        this.showPaymentDialog = true

        this.waitForPayment(this.paymentHash)

        Quasar.Notify.create({
          type: 'positive',
          message: 'Bet placed! Waiting for payment confirmation...'
        })
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async waitForPayment(paymentHash) {
      try {
        const url = new URL(window.location)
        url.protocol = url.protocol === 'https:' ? 'wss' : 'ws'
        url.pathname = `/api/v1/ws/${paymentHash}`
        const ws = new WebSocket(url)

        ws.addEventListener('message', async ({data}) => {
          const payment = JSON.parse(data)
          if (payment.pending === false) {
            Quasar.Notify.create({
              type: 'positive',
              message: 'Payment confirmed! Starting game...'
            })

            // Set the client seed to the payment hash for provably fair gameplay
            this.clientSeed = payment.payment_hash

            this.showPaymentDialog = false
            this.gameStatus = 'bet_placed'
            this.gameStarted = true

            this.listenForGameUpdates(this.currentHandsPlayedId)

            ws.close()
          }
        })
      } catch (err) {
        console.warn(err)
        Quasar.Notify.create({
          type: 'negative',
          message: 'Error waiting for payment.'
        })
      }
    },

    listenForGameUpdates(handsPlayedId) {
      try {
        const url = new URL(window.location)
        url.protocol = url.protocol === 'https:' ? 'wss' : 'ws'
        url.pathname = `/api/v1/ws/${handsPlayedId}`
        const ws = new WebSocket(url)

        ws.addEventListener('message', async ({data}) => {
          const gameData = JSON.parse(data)

          // Update the gameState object with new data, transforming card data as needed
          this.gameState = {
            ...this.gameState,
            ...gameData,
            player_hand: gameData.player_hand
              ? this.parseCards(gameData.player_hand)
              : this.gameState.player_hand,
            dealer_hand: gameData.dealer_hand
              ? this.parseCards(gameData.dealer_hand)
              : this.gameState.dealer_hand
          }

          // Calculate dealer's visible score (first card only) when not revealed
          if (this.gameState.dealer_hand.length > 0 && !this.dealerRevealed) {
            this.gameState.dealer_hidden_score = this.getCardValue(
              this.gameState.dealer_hand[0]
            )
          }

          // Update game status and handle completion
          if (gameData.status === 'completed') {
            this.gameFinished = true
            this.gameStatus = 'game_over'
            this.dealerRevealed = true

            // Set result message based on outcome
            if (gameData.outcome === 'player_wins') {
              this.resultMessage = 'You Win!'
              this.resultColor = 'green'
              confettiBothSides()
            } else if (gameData.outcome === 'dealer_wins') {
              this.resultMessage = 'Dealer Wins!'
              this.resultColor = 'red'
            } else if (gameData.outcome === 'push') {
              this.resultMessage = 'Push (Tie)!'
              this.resultColor = 'orange'
            }

            // Add game to history
            this.addGameToHistory(gameData)
          }
          console.log('Game update received:', this.gameState)
          console.log('Full game data:', gameData)
        })
      } catch (err) {
        console.warn(err)
      }
    },

    parseCards(cardsJson) {
      try {
        const cards = JSON.parse(cardsJson)
        return cards.map(card => ({
          rank: card.rank,
          suit: card.suit_symbol || card.suit
        }))
      } catch (e) {
        console.error('Error parsing cards:', e)
        return []
      }
    },

    async hit() {
      try {
        await LNbits.api.request(
          'POST',
          `/blackjack/api/v1/hands_played/${this.currentHandsPlayedId}/hit`,
          null
        )
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async stand() {
      try {
        await LNbits.api.request(
          'POST',
          `/blackjack/api/v1/hands_played/${this.currentHandsPlayedId}/stand`,
          null
        )
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    closePaymentDialog() {
      this.showPaymentDialog = false
    },

    getSuitSymbol(suitCode) {
      const suitMap = {
        H: '♥',
        D: '♦',
        C: '♣',
        S: '♠'
      }
      return suitMap[suitCode] || suitCode
    },

    getHandAbbreviation(hand, hideSecondCard = false) {
      if (!hand || hand.length === 0) return ''

      // If we need to hide the second card and there are 2 or more cards
      if (hideSecondCard && hand.length >= 2) {
        // Show only the first card
        return '(' + hand[0].rank + this.getSuitSymbol(hand[0].suit) + ' + ??)'
      }

      return (
        '(' +
        hand
          .map(card => card.rank + this.getSuitSymbol(card.suit))
          .join(' + ') +
        ')'
      )
    },

    getCardValue(card) {
      if (!card) return 0
      const rank = card.rank
      if (rank === 'A') return 11 // Ace initially counts as 11
      if (['K', 'Q', 'J'].includes(rank)) return 10 // Face cards count as 10
      return parseInt(rank) || 0 // Number cards count as face value
    },

    getOutcomeIcon(outcome) {
      if (outcome === 'player_wins') return 'sentiment_very_satisfied'
      if (outcome === 'dealer_wins') return 'sentiment_very_dissatisfied'
      if (outcome === 'push') return 'sentiment_neutral'
      return 'help_outline'
    },

    getOutcomeColor(outcome) {
      if (outcome === 'player_wins') return 'green'
      if (outcome === 'dealer_wins') return 'red'
      if (outcome === 'push') return 'orange'
      return 'grey'
    },

    formatOutcome(outcome) {
      if (outcome === 'player_wins') return 'Win'
      if (outcome === 'dealer_wins') return 'Loss'
      if (outcome === 'push') return 'Push'
      return outcome
    },

    getResultText(outcome) {
      if (outcome === 'player_wins') return 'You Won!'
      if (outcome === 'dealer_wins') return 'Dealer Won'
      if (outcome === 'push') return 'Push (Tie)'
      return outcome
    },

    addGameToHistory(gameData) {
      // Use the payout_amount from the API response
      const payoutAmount = gameData.payout_amount || 0

      const gameRecord = {
        id: gameData.id || this.currentHandsPlayedId,
        created_at: gameData.created_at || new Date().toISOString(),
        bet_amount: this.betAmount,
        payout_amount: payoutAmount,
        outcome: gameData.outcome,
        player_hand: gameData.player_hand
          ? this.parseCards(gameData.player_hand)
          : [...this.gameState.player_hand],
        dealer_hand: gameData.dealer_hand
          ? this.parseCards(gameData.dealer_hand)
          : [...this.gameState.dealer_hand],
        player_score:
          gameData.player_score !== undefined
            ? gameData.player_score
            : this.gameState.player_score,
        dealer_score:
          gameData.dealer_score !== undefined
            ? gameData.dealer_score
            : this.gameState.dealer_score,
        server_seed_hash:
          gameData.server_seed_hash || this.gameState.server_seed_hash,
        client_seed: gameData.client_seed || this.gameState.client_seed,
        server_seed: gameData.server_seed || this.gameState.server_seed // Only available after game completion
      }

      // Add to the beginning of the array to show most recent games first
      this.gameHistory.unshift(gameRecord)

      // Limit history to last 10 games to prevent memory issues
      if (this.gameHistory.length > 10) {
        this.gameHistory.pop()
      }
    },

    newGame() {
      this.gameStatus = 'waiting_for_bet'
      this.gameStarted = false
      this.gameFinished = false
      this.dealerRevealed = false
      this.resultMessage = ''
      this.resultColor = ''
      this.currentHandsPlayedId = null

      // Reset the gameState object to initial values
      this.gameState = {
        id: null,
        dealers_id: null,
        status: null,
        bet_amount: null,
        player_hand: [],
        dealer_hand: [],
        player_score: 0,
        dealer_score: 0,
        dealer_hidden_score: 0,
        outcome: null,
        payout_amount: 0,
        payout_sent: false,
        server_seed_hash: null,
        client_seed: null,
        server_seed: null,
        created_at: null,
        updated_at: null,
        ended_at: null,
        paid: false
      }
    }
  },
  created() {
    this.dealersId = dealersId
    this.betAmount = maxBet
    this.newGame()
  }
})
