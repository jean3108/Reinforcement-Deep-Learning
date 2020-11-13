import gym
import gridworld
import copy
import numpy as np
from collections import defaultdict
import utils as ut
import memory as mem
import torch
import pandas as pd
import torch.nn.functional as F



class DQNAgent(object):
    """Deep Qlearning"""

    def __init__(self, env, opt, episodes, batch_size, target_step, dim_layers, num_layers, test = False):
        self.nb_episodes = episodes
        self.opt = opt
        self.env = env
        if opt.fromFile is not None:
            self.load(opt.fromFile)

        self.lossFunc = torch.nn.SmoothL1Loss()
        self.targetStep = target_step
        self.batch_size = batch_size
        self.dim_layers = dim_layers
        self.num_layers = num_layers
        self.mem_size = 10000
        self.buffer = mem.ReplayBuffer(self.mem_size)
        self.test = test
        self.old_state = None
        self.old_act = None
        self.action_space = env.action_space
        self.featureExtractor = opt.featExtractor(env)
        self.qsa = ut.NN(self.featureExtractor.outSize, self.env.action_space.n, [dim_layers for i in range(num_layers)])
        self.optiQsa = torch.optim.Adam(params=self.qsa.parameters(),lr=1e-4)
        self.qsaTraget = copy.deepcopy(self.qsa)
        self.alpha = 0.1
        self.gamma = 0.99
        self.epsilon0 = 1
        self.mu = 10/self.nb_episodes

    def act(self, observation, reward, frame, episode, done):
        # Qtarget update
        if frame % self.targetStep == 0:
            self.setTarget(self.qsa)
        
        # Initialisation
        observation = torch.tensor(self.featureExtractor.getFeatures(observation), dtype=torch.float)
        qs = self.qsa(observation)

        if self.old_state == None:
            action = self.env.action_space.sample()
            self.old_state = observation
            self.old_act = action
            
            return action

        # epsilon greedy
        eps = self.epsilon0 / (1 + self.mu * episode)
        if np.random.rand() > eps or self.test == True:
            action = int(torch.argmax(qs))
        else:
            action = self.env.action_space.sample()
        

        # Remplissage du buffer
        self.buffer.add(self.old_state, self.old_act, reward, observation, done)
        
        # Apprentissage
        #if len(self.buffer) > self.batch_size and self.test == False: # start training when there is enough example 
        if len(self.buffer) == self.mem_size and self.test == False: # start training when buffer is full

            states, actions, rewards, next_states, dones = self.buffer.sample(self.batch_size)
            loss = self.train_step(states, actions, rewards, next_states, dones)
            loss.backward()
            self.optiQsa.step()
            self.optiQsa.zero_grad()

        # Update state and action
        self.old_state = observation
        self.old_act = action
            
        return action
    
    def train_step(self,states, actions, rewards, next_states, dones):
        """Perform a training iteration on a batch of data sampled from the experience
        replay buffer.
        """
        # Calculate targets.
        max_next_qs = self.qsaTraget(next_states).max(-1).values
        with torch.no_grad():
            target = rewards + (1.0 - dones) * self.gamma * max_next_qs
        qs = self.qsa(states)
        action_masks = F.one_hot(actions, self.env.action_space.n)
        masked_qs = (action_masks * qs).sum(dim=-1)
        loss = self.lossFunc(masked_qs, target.detach())
        #nn.utils.clip_grad_norm_(loss, max_norm=10)

        return loss


    def setTarget(self, target):
        self.qsaTraget = copy.deepcopy(target)
    
    def save(self,outputDir):
        pass
    
    def load(self,inputDir):
        pass



class PolicyGradAgent(object):
    """Policy Gradient agent"""

    def __init__(self, env, opt, episodes, batch_size, target_step, dim_layers, num_layers, lr1, lr2, mu, test = False, loss_Func = 0):
        self.nb_episodes = episodes
        self.opt = opt
        self.env = env
        if opt.fromFile is not None:
            self.load(opt.fromFile)

        self.lossFuncs = [torch.nn.MSELoss(), torch.nn.SmoothL1Loss()]
        self.lossFunc = self.lossFuncs[loss_Func]
        self.targetStep = target_step
        self.batch_size = batch_size
        self.dim_layers = dim_layers
        self.num_layers = num_layers
        self.buffer = mem.ReplayBuffer(self.batch_size)
        self.test = test
        self.old_state = None
        self.old_act = None
        self.action_space = env.action_space
        self.featureExtractor = opt.featExtractor(env)
        self.vpi = ut.NN(self.featureExtractor.outSize, 1, [dim_layers for i in range(num_layers)]) # state value
        self.policy = ut.Policy_NN(self.featureExtractor.outSize, env.action_space.n, [dim_layers for i in range(num_layers)]) # Policy 
        #self.net = ut.Policy_NN_2(self.featureExtractor.outSize, env.action_space.n)
        #self.optim = torch.optim.Adam(params=self.net.parameters(),lr=1e-2)
        self.vpiTarget = copy.deepcopy(self.vpi)
        #self.netTarget = copy.deepcopy(self.net)
        self.optiVpi = torch.optim.Adam(params=self.vpi.parameters(),lr=lr1)
        self.optiPolicy = torch.optim.Adam(params=self.policy.parameters(),lr=lr2)
        self.alpha = 0.1
        self.gamma = 0.99
        self.epsilon0 = 1
        self.mu = mu/self.nb_episodes

    def act(self, observation, reward, frame, episode, done):

        # Qtarget update
        #if frame % self.targetStep == 0:
            #self.setTarget(self.vpi) 

        
        # Initialisation
        observation = torch.tensor(self.featureExtractor.getFeatures(observation), dtype=torch.float)
        probas = self.policy(observation)
        #probas, _ = self.net(observation)

        if self.old_state == None:
            
            action = self.env.action_space.sample()
            self.old_state = observation
            self.old_act = action
            
            return action

        # epsilon greedy
        eps = self.epsilon0 / (1 + self.mu * episode)
        if np.random.rand() > eps or self.test == True:
            action = int(torch.argmax(probas))

        else:
            action = self.env.action_space.sample()

        # Remplissage du buffer
        self.buffer.add(self.old_state, self.old_act, reward, observation, done)

        # Apprentissage des Vpi
        if len(self.buffer) == self.batch_size and self.test == False:

            states, actions, rewards, next_states, dones = self.buffer.sample(self.batch_size)
            critic_loss = self.train_step_vpi(states, actions, rewards, next_states, dones)
            
            # Campute advantage
            advantage = rewards + (1.0 - dones) * self.gamma * self.vpi(next_states).squeeze() - self.vpi(states).squeeze()

            # Compute reward expectation gradient

            # 1) compute expectation
            action_masks = F.one_hot(actions, self.env.action_space.n)
            masked_log_proba = (action_masks * self.policy(states)).sum(dim=-1)
            actor_loss = torch.sum(masked_log_proba*advantage.detach()) 

            # 2) back propagation
            

            # 3) Update parameters and reset buffer
            self.optiPolicy.zero_grad() # clear Policy params gradient
            self.optiVpi.zero_grad() # clear Vpi params gradient
            actor_loss.backward()
            critic_loss.backward()
            self.optiPolicy.step()
            self.optiVpi.step()
            
            """
            loss = self.train_step(states, actions, rewards, next_states, dones)
            loss.backward()
            self.optim.step()
            self.optim.zero_grad()
            """
            self.setTarget(self.vpi)
            self.resetBuffer() # reset buffer to sample with next step policy

        # Update state and action
        self.old_state = observation
        self.old_act = action
            
        return action

    def train_step_vpi(self,states, actions, rewards, next_states, dones):
        """Perform a training iteration on a batch of data sampled from the experience
        replay buffer.
        """
        # Calculate targets.
        vpi = self.vpi(states).squeeze()
        with torch.no_grad():
            next_vpi = self.vpiTarget(next_states).squeeze()
            target = rewards + (1.0 - dones) * self.gamma * next_vpi   
        loss_vpi = self.lossFunc(vpi, target.detach())

        return loss_vpi

    def train_step(self,states, actions, rewards, next_states, dones):
        """Perform a training iteration on a batch of data sampled from the experience
        replay buffer.
        """
        
        log_proba, vpi = self.net(states)

        # Critic loss.
        with torch.no_grad():
            _, next_vpi = self.net(next_states)
            target = rewards + (1.0 - dones) * self.gamma * next_vpi.squeeze()
        loss_vpi = self.lossFunc(vpi.squeeze(), target.detach())
        A = rewards + (1.0 - dones) * self.gamma * next_vpi.squeeze() - vpi.squeeze()

        # Actor loss
        action_masks = F.one_hot(actions, self.env.action_space.n)
        masked_log_proba = (action_masks * log_proba).sum(dim=-1)
        loss_policy = torch.sum(masked_log_proba*A)

        loss = loss_vpi + loss_policy

        return loss


    def setTarget(self, target):
        self.vpiTarget = copy.deepcopy(target)

    def resetBuffer(self):
        self.buffer = mem.ReplayBuffer(self.batch_size)
    
    def save(self,outputDir):
        pass
    
    def load(self,inputDir):
        pass