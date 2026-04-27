window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data: function () {
    return {
      currencyOptions: ['sat'],
      settingsFormDialog: {
        show: false,
        data: {}
      },

      dealersFormDialog: {
        show: false,
        data: {
          name: null,
          wallet_id: null,
          min_bet: null,
          max_bet: null,
          decks: null,
          hit_soft_17: true, // Default: dealer hits on soft 17
          blackjack_payout: '3:2', // Default: standard 3:2 payout
          active: true // Default: dealer is active
        }
      },
      dealersList: [],
      dealersTable: {
        search: '',
        loading: false,
        columns: [
          {
            name: 'name',
            align: 'left',
            label: 'Name',
            field: 'name',
            sortable: true
          },
          {
            name: 'wallet_id',
            align: 'left',
            label: 'Wallet',
            field: 'wallet_id',
            sortable: true
          },
          {
            name: 'min_bet',
            align: 'left',
            label: 'Min. Bet',
            field: 'min_bet',
            sortable: true
          },
          {
            name: 'max_bet',
            align: 'left',
            label: 'Max. Bet',
            field: 'max_bet',
            sortable: true
          },
          {
            name: 'decks',
            align: 'left',
            label: 'Num. of Decks',
            field: 'decks',
            sortable: true
          },
          {
            name: 'hit_soft_17',
            align: 'left',
            label: 'H17',
            field: 'hit_soft_17',
            sortable: true
          },
          {
            name: 'blackjack_payout',
            align: 'left',
            label: 'blackjack_payout',
            field: 'blackjack_payout',
            sortable: true
          },
          {
            name: 'active',
            align: 'left',
            label: 'Active',
            field: 'active',
            sortable: true
          },
          {
            name: 'updated_at',
            align: 'left',
            label: 'Updated At',
            field: 'updated_at',
            sortable: true
          },
          {name: 'id', align: 'left', label: 'ID', field: 'id', sortable: true}
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      },
      handsPlayedList: [],
      handsPlayedTable: {
        search: '',
        loading: false,
        columns: [
          {
            name: 'dealer',
            align: 'left',
            label: 'Dealer',
            field: 'dealers_id',
            sortable: true,
            format: val => {
              const dealer = this.dealersList.find(d => d.id === val)
              return dealer ? dealer.name || dealer.id : val
            }
          },
          {
            name: 'status',
            align: 'left',
            label: 'Status',
            field: 'status',
            sortable: true
          },
          {
            name: 'bet',
            align: 'left',
            label: 'Bet',
            field: 'bet_amount',
            sortable: true
          },
          {
            name: 'payment_hash',
            align: 'left',
            label: 'Payment Hash',
            field: 'payment_hash',
            sortable: true,
            format: val => val && `${val.slice(0, 6)}...${val.slice(-6)}`
          },
          {
            name: 'outcome',
            align: 'left',
            label: 'Outcome',
            field: 'outcome',
            sortable: true
          },
          {
            name: 'server_seed_hash',
            align: 'left',
            label: 'Server Seed Hash',
            field: 'server_seed_hash',
            sortable: true
          },
          {
            name: 'ended_at',
            align: 'left',
            label: 'Ended At',
            field: 'ended_at',
            sortable: true
          },
          {
            name: 'paid',
            align: 'left',
            label: 'Paid',
            field: 'paid',
            sortable: true
          },
          {
            name: 'payout_sent',
            align: 'left',
            label: 'Payout Sent',
            field: 'payout_sent',
            sortable: true
          },
          {
            name: 'payout_to',
            align: 'left',
            label: 'Payout To',
            field: 'lnaddress',
            sortable: true
          },
          {
            name: 'updated_at',
            align: 'left',
            label: 'Updated At',
            field: 'updated_at',
            sortable: true
          },
          {name: 'ID', align: 'left', label: 'ID', field: 'id', sortable: true}
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      }
    }
  },
  watch: {
    'dealersTable.search': {
      handler() {
        const props = {}
        if (this.dealersTable.search) {
          props['search'] = this.dealersTable.search
        }
        this.getDealers()
      }
    },
    'handsPlayedTable.search': {
      handler() {
        const props = {}
        if (this.handsPlayedTable.search) {
          props['search'] = this.handsPlayedTable.search
        }
        this.getHandsPlayed()
      }
    }
  },

  methods: {
    //////////////// Settings ////////////////////////
    async updateSettings() {
      try {
        const data = {...this.settingsFormDialog.data}

        await LNbits.api.request(
          'PUT',
          '/blackjack/api/v1/settings',
          null,
          data
        )
        this.settingsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async getSettings() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/blackjack/api/v1/settings',
          null
        )
        this.settingsFormDialog.data = data
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async showSettingsDataForm() {
      await this.getSettings()
      this.settingsFormDialog.show = true
    },

    //////////////// Dealers ////////////////////////
    async showNewDealersForm() {
      this.dealersFormDialog.data = {
        name: null,
        wallet_id: null,
        min_bet: null,
        max_bet: null,
        decks: null,
        hit_soft_17: true, // Default: dealer hits on soft 17
        blackjack_payout: '3:2', // Default: standard 3:2 payout
        active: true // Default: dealer is active
      }
      this.dealersFormDialog.show = true
    },
    async showEditDealersForm(data) {
      this.dealersFormDialog.data = {...data}
      this.dealersFormDialog.show = true
    },
    async saveDealers() {
      try {
        const data = {extra: {}, ...this.dealersFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/blackjack/api/v1/dealers' + entry,
          null,
          data
        )
        this.getDealers()
        this.dealersFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getDealers(props) {
      try {
        this.dealersTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(this.dealersTable, props)
        const {data} = await LNbits.api.request(
          'GET',
          `/blackjack/api/v1/dealers/paginated?${params}`,
          null
        )
        this.dealersList = data.data
        this.dealersTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.dealersTable.loading = false
      }
    },
    async deleteDealers(dealersId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Dealers?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/blackjack/api/v1/dealers/' + dealersId,
              null
            )
            await this.getDealers()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async exportDealersCSV() {
      await LNbits.utils.exportCSV(
        this.dealersTable.columns,
        this.dealersList,
        'dealers_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Hands Played ////////////////////////
    async getHandsPlayed(props) {
      try {
        this.handsPlayedTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(
          this.handsPlayedTable,
          props
        )
        const {data} = await LNbits.api.request(
          'GET',
          `/blackjack/api/v1/hands_played/paginated?${params}`
        )
        this.handsPlayedList = data.data
        this.handsPlayedTable.pagination.rowsNumber = data.total
      } catch (error) {
        console.error(`Error fetching hands played: ${error}`)
        LNbits.utils.notifyApiError(error)
      } finally {
        this.handsPlayedTable.loading = false
      }
    },
    async deleteHandsPlayed(handsPlayedId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Hands Played?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/blackjack/api/v1/hands_played/' + handsPlayedId,
              null
            )
            await this.getHandsPlayed()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },

    async exportHandsPlayedCSV() {
      await LNbits.utils.exportCSV(
        this.handsPlayedTable.columns,
        this.handsPlayedList,
        'hands_played_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    }
  },
  ///////////////////////////////////////////////////
  //////LIFECYCLE FUNCTIONS RUNNING ON PAGE LOAD/////
  ///////////////////////////////////////////////////
  async created() {
    this.getDealers()
    this.getHandsPlayed()
  }
})
