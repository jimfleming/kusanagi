import os,sys
from datetime import datetime

import random
import numpy as np
import theano
import theano.tensor as T
from theano.sandbox.linalg import psd,matrix_inverse

def maha(X1,X2=None,M=None, all_pairs=True):
    ''' Returns the squared Mahalanobis distance'''
    D = []
    deltaM = []
    if X2 is None:
        X2 = X1
    
    if all_pairs:
        if M is None:
            #D, updts = theano.scan(fn=lambda xi,X: T.sum((xi-X)**2,1), sequences=[X1], non_sequences=[X2])
            #D = ((X1-X2[:,None,:])**2).sum(2)
            D = T.sum(X1**2,1)[:,None] + T.sum(X2**2,1) - 2*X1.dot(X2.T);
        else:
            #D, updts = theano.scan(fn=lambda xi,X,V: T.sum(((xi-X).dot(V))*(xi-X),1), sequences=[X1], non_sequences=[X2,M])
            #delta = (X1-X2[:,None,:])
            #D = ((delta.dot(M))*delta).sum(2)
            X1M = X1.dot(M);
            D = T.sum(X1M*X1,1)[:,None] + T.sum(X2.dot(M)*X2,1) - 2*X1M.dot(X2.T)
    else:
        # computes the distance  x1i - x2i for each row i
        if X1 is X2:
            # in this case, we don't need to compute anything
            D = T.zeros((X1.shape[0],))
            return D
        delta = X1-X2
        if M is None:
            deltaM = delta
        else:
            deltaM = delta.dot(M)
        D = T.sum(deltaM*delta,1)
    return D

def print_with_stamp(message, name=None, same_line=False):
    out_str = ''
    if name is None:
        out_str = '[%s] %s'%(str(datetime.now()),message)
    else:
        out_str = '[%s] %s > %s'%(str(datetime.now()),name,message)
    
    if same_line:
        sys.stdout.write('\r'+out_str)
    else:
        sys.stdout.write(out_str)
        print ''
    sys.stdout.flush()

def kmeanspp(X,k):
    import random
    N,D = X.shape
    c = [ X[random.randint(0,N)] ]
    d = np.full((k,N),np.inf)
    while len(c) < k:
        i = len(c) - 1
        # get distance from dataset to latest center
        d[i] =  np.sum((X-c[i])**2,1)
        # get minimum distances
        min_dists = d[:i+1].min(0)
        # select next center with probability proportional to the inverse minimum distance
        selection_prob = np.cumsum(min_dists/min_dists.sum())
        r = random.uniform(0,1)
        j = np.searchsorted(selection_prob,r)
        c.append(X[j])

    return np.array(c)

def gTrig(x,angi,D):
    Da = 2*len(angi)
    n = x.shape[0]
    xang = T.zeros((n,Da))
    xi = x[:,angi]
    xang = T.set_subtensor(xang[:,::2], T.sin(xi))
    xang = T.set_subtensor(xang[:,1::2], T.cos(xi))

    non_angle_dims = list(set(range(D)).difference(angi))
    if len(non_angle_dims)>0:
        xnang = x[:,non_angle_dims]
        m = T.concatenate([xnang,xang],axis=1)
    else:
        m = xang
    return m

def gTrig2(m, v, angi, D, derivs=False):
    non_angle_dims = list(set(range(D)).difference(angi))
    Da = 2*len(angi)
    Dna = len(non_angle_dims)
    Ma = T.zeros((Da,))
    Va = T.zeros((Da,Da))
    Ca = T.zeros((D,Da))

    # compute the mean
    mi = m[angi]
    vi = v[angi,:][:,angi]
    vii = v[angi,angi]
    exp_vii_h = T.exp(-vii/2)

    Ma = T.set_subtensor(Ma[::2], exp_vii_h*T.sin(mi))
    Ma = T.set_subtensor(Ma[1::2], exp_vii_h*T.cos(mi))
    
    # compute the entries in the augmented covariance matrix
    vii_c = vii[:,None]
    vii_r = vii[None,:]
    lq = -0.5*(vii_c+vii_r); q = T.exp(lq)
    exp_lq_p_vi = T.exp(lq+vi)
    exp_lq_m_vi = T.exp(lq-vi)
    mi_c = mi[:,None]
    mi_r = mi[None,:]
    U1 = (exp_lq_p_vi - q)*(T.sin(mi_c-mi_r))
    U2 = (exp_lq_m_vi - q)*(T.sin(mi_c+mi_r))
    U3 = (exp_lq_p_vi - q)*(T.cos(mi_c-mi_r))
    U4 = (exp_lq_m_vi - q)*(T.cos(mi_c+mi_r))
    
    Va = T.set_subtensor(Va[::2,::2], U3-U4)
    Va = T.set_subtensor(Va[1::2,1::2], U3+U4)
    U12 = U1+U2
    Va = T.set_subtensor(Va[::2,1::2],U12)
    Va = T.set_subtensor(Va[1::2,::2],U12.T)
    Va = 0.5*Va

    # inv times input output covariance
    Is = 2*np.arange(len(angi)); Ic = Is +1;
    Ca = T.set_subtensor( Ca[angi,Is], Ma[1::2]) 
    Ca = T.set_subtensor( Ca[angi,Ic], -Ma[::2]) 

    # construct mean vectors ( non angle dimensions come first, then angle dimensions)
    Mna = m[non_angle_dims]
    M = T.concatenate([Mna,Ma])

    # construct the corresponding covariance matrices ( just the blocks for the non angle dimensions and the angle dimensions separately)
    V = T.zeros((Dna+Da,Dna+Da))
    Vna = v[non_angle_dims,:][:,non_angle_dims]
    V = T.set_subtensor(V[:Dna,:Dna], Vna)
    V = T.set_subtensor(V[Dna:,Dna:], Va)

    # fill in the cross covariances
    q = v.dot(Ca)[non_angle_dims,:]
    V = T.set_subtensor(V[:Dna,Dna:], q )
    V = T.set_subtensor(V[Dna:,:Dna], q.T )

    retvars = [M,V,Ca]

    # compute derivatives
    if derivs:
        dretvars = []
        for r in retvars:
            dretvars.append( T.jacobian(r.flatten(),m) )
        for r in retvars:
            dretvars.append( T.jacobian(r.flatten(),v) )
        retvars.extend(dretvars)

    return retvars

def gTrig_np(x,angi):
    if type(x) is list:
        x = np.array(x)
    if x.ndim == 1:
        x = x[None,:]
    D = x.shape[1]
    Da = 2*len(angi)
    n = x.shape[0]
    xang = np.zeros((n,Da))
    xi = x[:,angi]
    xang[:,::2] =  np.sin(xi)
    xang[:,1::2] =  np.cos(xi)

    non_angle_dims = list(set(range(D)).difference(angi))
    xnang = x[:,non_angle_dims]
    m = np.concatenate([xnang,xang],axis=1)

    return m

def gTrig2_np(m,v,angi,D):
    non_angle_dims = list(set(range(D)).difference(angi))
    Da = 2*len(angi)
    Dna = len(non_angle_dims) 
    n = m.shape[0]
    Ma = np.zeros((n,Da))
    Va = np.zeros((n,Da,Da))
    Ca = np.zeros((n,D,Da))
    Is = 2*np.arange(len(angi)); Ic = Is +1;

    # compute the mean
    mi = m[:,angi]
    vi = (v[:,angi,:][:,:,angi])
    vii = (v[:,angi,angi])
    exp_vii_h = np.exp(-vii/2)
    
    Ma[:,::2] = exp_vii_h*np.sin(mi)
    Ma[:,1::2] = exp_vii_h*np.cos(mi)
    
    # compute the entries in the augmented covariance matrix
    lq = -0.5*(vii[:,:,None]+vii[:,None,:]); q = np.exp(lq)
    exp_lq_p_vi = np.exp(lq+vi)
    exp_lq_m_vi = np.exp(lq-vi)
    U1 = (exp_lq_p_vi - q)*(np.sin(mi[:,:,None]-mi[:,None,:]))
    U2 = (exp_lq_m_vi - q)*(np.sin(mi[:,:,None]+mi[:,None,:]))
    U3 = (exp_lq_p_vi - q)*(np.cos(mi[:,:,None]-mi[:,None,:]))
    U4 = (exp_lq_m_vi - q)*(np.cos(mi[:,:,None]+mi[:,None,:]))
    
    Va[:,::2,::2] = U3-U4
    Va[:,1::2,1::2] = U3+U4
    Va[:,::2,1::2] = U1+U2
    Va[:,1::2,::2] = Va[:,::2,1::2].transpose(0,2,1)
    Va = 0.5*Va

    # inv times input output covariance
    Ca[:,angi,Is] = Ma[:,1::2]
    Ca[:,angi,Ic] = -Ma[:,::2] 

    # construct mean vectors ( non angle dimensions come first, then angle dimensions)
    Mna = m[:, non_angle_dims]
    M = np.concatenate([Mna,Ma],axis=1)

    # construct the corresponding covariance matrices ( just the blocks for the non angle dimensions and the angle dimensions separately)
    V = np.zeros((n,Dna+Da,Dna+Da))
    Vna = v[:,non_angle_dims,:][:,:,non_angle_dims]
    V[:,:Dna,:Dna] = Vna
    V[:,Dna:,Dna:] = Va

    # fill in the cross covariances
    V[:,:Dna,Dna:] = (v[:,:,:,None]*Ca[:,:,None,:]).sum(1)[:,non_angle_dims,:] 
    V[:,Dna:,:Dna] = V[:,:Dna,Dna:].transpose(0,2,1)

    return [M,V]

def get_compiled_gTrig(angi,D,derivs=True):
    m = T.dvector('x')      # n_samples x idims
    v = T.dmatrix('x_cov')  # n_samples x idims x idims

    gt = gTrig2(m, v, angi, D, derivs=derivs)
    return theano.function([m,v],gt)

def wrap_params(p_list):
    # flatten out and concatenate the parameters
    P = []
    for pi in p_list:
        P.append(pi.flatten())
    P = np.concatenate(P)
    return P
    
def unwrap_params(P,parameter_shapes):
    # get the correct sizes for the parameters
    p = []
    i = 0
    for pshape in parameter_shapes:
        # get the number of elemebt for current parameter
        npi = reduce(lambda x,y: x*y, pshape)
        # select corresponding elements and reshape into appropriate shape
        p.append( P[i:i+npi].reshape(pshape) )
        # set index to the beginning  of next parameter
        i += npi
    return p

class MemoizeJac(object):
    def __init__(self, fun):
        self.fun = fun
        self.value, self.jac = None, None
        self.x = None

    def _compute(self, x, *args):
        self.x = np.asarray(x).copy()
        self.value, self.jac = self.fun(x, *args)

    def __call__(self, x, *args):
        if self.value is not None and np.alltrue(x == self.x):
            return self.value
        else:
            self._compute(x, *args)
            return self.value

    def derivative(self, x, *args):
        if self.jac is not None and np.alltrue(x == self.x):
            return self.jac
        else:
            self._compute(x, *args)
            return self.jac
