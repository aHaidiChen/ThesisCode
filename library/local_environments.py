import numpy as np
import copy

class agent_environment:
    '''Local Environment for a trading agent using market orders'''
    def __init__(self, 
        market, 
        position, # Position to exit
        n_trades, # Number of trades
        action_values_pct # Actions corresponding to the percentage of stock to sell
        ):
        
        # Parameters
        self.state_size = 2 # consolidate this

        # Market environment
        self.m = market
        self.market_data = (self.m.n_hist_prices > 0) # bool: use market data

        # Local environment
        self.initial_position =  position
        self.step_size = 1 / n_trades # depreciated?
        self.reset()

        ### TEMP
        self.debug = False
        
        #### Overhaul of the trading system, to enable set below to True ####
        
        # Instead trade every second but make decisions every self.trade_frequency seconds
        self.trade_by_second = True
        self.n_trades = n_trades
        self.trade_freq = int(self.m.stock.n_steps / self.n_trades) # in seconds
        print("trade freq",self.trade_freq)
        self.step_size = 1 / (self.n_trades * self.trade_freq)

         # Possible amounts to sell: 0 - 10% of the total position
        self.action_values = np.array(action_values_pct) * position / (n_trades * self.trade_freq)
        self.num_actions = len(self.action_values)

        #### End ####


    def sell(self,volume):
        capped_volume = np.minimum(volume,self.position)
        self.position -= capped_volume
        returns = self.m.sell(capped_volume,self.step_size) 
        self.cash += returns
        return returns, capped_volume

    def reset(self,training = True):
        self.position = self.initial_position
        self.cash = 0
        self.time = -1 # Time runs from -1 to 1
        self.m.reset(self.step_size,training)
        return self.state()

    def state(self,full = False):
        res = [2 * self.position/self.initial_position - 1,self.time]
        res = np.reshape(res,(1,len(res)))
        if self.market_data:
            market_state = self.m.state()
            new_state = None
            for mstate in market_state:
                if new_state is None:
                    new_state = mstate
                    continue
                new_state = np.vstack((new_state,mstate))
            new_state = np.transpose(new_state)
            full_res = [res,np.reshape(new_state,(1,new_state.shape[0],len(self.m.hist)))]
            return copy.deepcopy(full_res)
        return copy.deepcopy(res)
    
    def step(self,action):
        '''Mechanism by which agent interacts with the environment.
        Arguments: action'''

        if self.trade_by_second:
            # Provides the option for the same action to be taken over the following n seconds
            total_rewards = 0
            total_amount = 0
            # We need to check whether in the next set of trade_freq trades we will
            # have reached the end of the trading period
            time_out = (round(self.time + self.trade_freq * 2 * self.step_size,7) >= 1)
            if time_out:
                if self.state_size == 2:
                    trade_size = self.position / self.trade_freq
                else:
                    trade_size = [self.position / self.trade_freq,0]
            else:
                trade_size = self.action_values[action]

            for t in range(self.trade_freq):
                self.m.progress(self.step_size)
                self.time += 2 * self.step_size

                
                # If we are in the final trading window we must trade position/trade_freq at each trade
                
                if self.state_size == 2:
                    rewards, amount  = self.sell(trade_size)
                else:
                    # Here we haven't considered the possibility that we may be able to execute LOs
                    # in this intra agent action window
                    rewards, amount, _  = self.sell(trade_size)
                if self.debug:
                    print("Selling",trade_size,"for",rewards)
                
                total_rewards += rewards
                total_amount += amount
                done = (self.position <= 0)
                if self.position < 0:
                    print("Warning position is ",self.position)
                if done:
                    break

            done = (self.position <= 0) + time_out
            rewards = self.scale_rewards(total_rewards,total_amount)
            #print("rewards",rewards)

        else:
            self.m.progress(self.step_size)
            self.time += 2 * self.step_size

            time_out = (round(self.time,7) >= 1)
            
            if time_out:
                if self.state_size == 2:
                    rewards, amount  = self.sell(self.position)
                else:
                    rewards, amount, _  = self.sell([self.position,0])
            else:
                rewards, amount, _ = self.sell(self.action_values[action])
            
            done = (self.position <= 0) + time_out
            if self.position < 0:
                print("Warning position is ",self.position)

            rewards = self.scale_rewards(rewards,amount)
        if self.debug:
            print("total rewards", rewards)
        return self.state(), rewards, done


    def scale_rewards(self,rewards,amount):
        return (rewards) / (self.initial_position ) # /* self.m.stock.initial

class orderbook_environment(agent_environment):
    '''Local Environment for a trading agent using both limit orders and market orders'''
    def __init__(self, market, position, n_trades, action_values_pct):
        
        self.lo_size_scaling = 500000 # How do we decide on this scaling factor?
        self.mo_size_scaling = 1000 # How do we decide on this scaling factor?
        # Probably lose info if this was done dynamically depending on episode

        super(orderbook_environment,self).__init__(market,position,n_trades,action_values_pct)
        self.state_size = 3 # position, time, bid, ask, bidSize, askSize, loPos
        #self.lo_action_values = np.array(lo_action_values_pct) * position / n_trades
        

    # Depreciated?
    def place_limit_order(self,size):
        print("WARNING: Using depreciated function (place_limit_order)!")
        # WARNING order capping must take place at agent level
        returns = self.m.place_limit_order(size)
        self.cash -= returns
        return returns

    def state(self):
        '''Returns the current state of the agent as a tuple with the following values:
        position (scaled), time (scaled), bid (scaled by market), ask (scaled by market),
        askSize, bidSize, total value of agents limit orders'''

        # How should bidSize and askSize be scaled?
        # We need to scale them in this function, not at market level as they have a
        # directly interpretable value there.
        res = [2 * self.position/self.initial_position - 1,
                self.time,
                self.m.lo_total_pos / self.initial_position - 0.5]
        res = np.reshape(res,(1,len(res)))
        if self.market_data:
            market_state = self.m.state()
            new_state = None
            for mstate in market_state:
                if new_state is None:
                    new_state = mstate
                    continue
                new_state = np.vstack((new_state,mstate))
            new_state = np.transpose(new_state)
            full_res = [res,np.reshape(new_state,(1,new_state.shape[0],new_state.shape[1]))]
            return full_res
        
        return res

    def sell(self,volume):
        # For the orderbook agent volume is a 2 tuple containing MO and LO volume
        # First update LOB...
        delta_position, returns = self.m.execute_lob(self.position)
        self.position -= delta_position
        # ... then execute any market orders ...
        #print("volume",volume)
        capped_mo_volume = np.minimum(volume[0],self.position)
        self.position -= capped_mo_volume
        returns += self.m.sell(capped_mo_volume,self.step_size) 
        if returns < 0:
            print("returns",returns,"position",self.position,"capped_mo_volume",capped_mo_volume)

        # ... then add limit orders up to remaining position - currently standing LOs
        capped_lo_volume = np.max(np.minimum(volume[1],self.position - self.m.lo_total_pos),0)
        self.m.place_limit_order(capped_lo_volume)
        self.cash += returns
        assert self.position >= 0, "Position cannot be negative"
        # To avoid agents "remembering" order sizes wrongly we must adjust volume within act
        return returns, capped_mo_volume, capped_lo_volume




    

