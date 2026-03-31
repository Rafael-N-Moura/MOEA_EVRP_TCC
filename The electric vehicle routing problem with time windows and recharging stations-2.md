

The Electric Vehicle Routing Problem with Time Windows and Recharging
## Stations
## Michael Schneider, Andreas Stenger, Dominik Goeke
## Technical Report 02/2012
## Michael Schneider
Chair of Business Information Systems and Operations Research
University of Kaiserslautern
schneider@wiwi.uni-kl.de
## Andreas Stenger
Chair of IT-based Logistics, Institute of Information Systems
Goethe University, Frankfurt am Main
stenger@wiwi.uni-frankfurt.de
## Dominik Goeke
Chair of Business Information Systems and Operations Research
University of Kaiserslautern
goeke@wiwi.uni-kl.de
University of Kaiserslautern
Chair of Business Information Systems and Operations Research (BISOR)
P.O. Box 3049
Erwin-Schr ̈odinger-Straße, Building 42-420
## 67653 Kaiserslautern, Germany
## Email:bisor@bisor.de, Web:http://bisor.de

The Electric Vehicle Routing Problem with Time Windows and
## Recharging Stations
## Abstract
Driven by new laws and regulations concerning the emission of greenhouse gases, carriers are starting
to use battery electric vehicles (BEVs) for last-mile deliveries.  The limited battery capacities of BEVs
necessitate visits to recharging stations during delivery tours of industry-typical length, which have to be
considered in the route planning in order to avoid inefficient vehicle routes with long detours. We introduce
the Electric Vehicle Routing Problem with Time Windows and Recharging Stations (E-VRPTW), which
incorporates the possibility of recharging at any of the available stations using an appropriate recharging
scheme.  Furthermore, we consider limited vehicle freight capacities as well as customer time windows,
which are the most important constraints in real-world logistics applications.  As solution method,  we
present a hybrid heuristic, that combines a Variable Neighborhood Search algorithm with a Tabu Search
heuristic.   Tests  performed  on  newly  designed  instances  for  the  E-VRPTW  as  well  as  on  benchmark
instances of related problems demonstrate the high performance of the heuristic proposed as well as the
positive effect of the hybridization.
## 1  Introduction
In recent years, the greenhouse effect has become a hot political topic worldwide and laws and
regulations to reduce greenhouse gas pollution have already been passed or are currently under
debate.   For  example,  to  stop  the  increasing  emissions  of  light  commercial  vehicles  (<3.5t),
EU regulation No 510/2011 imposes a penalty of 95 Euro for each gram CO
## 2
/km above 147 g
## CO
## 2
/km of the manufacturers’ average emissions starting in 2020 (European Parliament and
European Council 2011).  The white book of the European Commission even envisages a mostly
emission-free city logistics until 2030 (European Comission 2011).
Such  political  decisions  and  visions  have  a  strong  effect  on  the  logistics  industry.   Many
logistics companies have already started to establish “Green Logistics” projects to reduce CO2
emissions.   Often,  their  first  step  is  an  increased  application  of  optimization  methods  to  im-
prove route planning, which helps to decrease the traveled distance of their vehicles and hence
emissions.  However, this generally yields a decline of emissions of only a few percent and the
emission level of their trucks and vans remains on a high level.
A more promising alternative is the use of battery electric vehicles (BEVs), which EU regu-
lation No 510/2011 defines to have zero emissions.  BEVs failed in earlier years due to exorbitant
battery prices and very short driving ranges.  However, as BEVs have become one of the major
research areas in the automotive sector and more and more BEVs are developed,  the magni-
tude of these problems diminishes.  In the small package shipping (SPS) industry, several big
companies,  like  DHL,  UPS,  DPD  and  Japan  Post,  already  started  using  BEVs  for  last-mile
deliveries from depots to customers, in particular in urban areas.  This causes new challenges for
an efficient route planning due to several specifics of BEVs.  For example, the maximum driving
range  of  BEVs  is  still  not  sufficient  to  perform  the  typical  delivery  tours  of  a  small  package
shipper in one run.  Since reducing the number of deliveries performed by one vehicle is clearly
not a profitable option, visits to recharging stations along the routes are required.  The number
## 1

of available recharging stations is still relatively scarce, which might lead to long detours if the
recharging requirements are not integrated into the route planning.
Route  planning  issues  of  logistics  companies  are  generally  represented  as  Vehicle  Routing
Problem  (VRP),  which  seeks  to  minimize  transportation  costs  for  visiting  customers,  while
every customer is visited exactly once and routes start and end at one depot.  The original VRP
was introduced by Dantzig and Ramser (1959) and over the years, many varieties and extensions
of the VRP have been proposed to incorporate real-world constraints and conditions.  Two of
the most widely studied extensions are the Capacitated VRP (CVRP), where vehicles have a
limited freight capacity and the VRP with Time Windows (VRPTW), where customers have to
be reached within a specified time interval (Laporte 2009, Nagata et al. 2010).  However, to the
best of our knowledge, only one routing model that considers recharging stations exists.  Erdogan
and Miller-Hooks (2012) propose the Green VRP (G-VRP), a routing model for Alternative Fuel
Vehicles (AFVs).  The G-VRP considers a limited fuel capacity of the vehicles and the possibility
to refuel at Alternative Fuel Stations (AFSs).  For each refueling as well as for each customer
visit, a fixed service time is considered and the maximum duration of a route is restricted.
Logistics providers using BEVs for last-mile deliveries require the incorporation of their most
important practical constraints into routing models for electric vehicles.  First, vehicle capacity
restrictions have to be considered for a significant share of delivery operations.  Second, many
companies, e.g., in the SPS sector, face a high percentage of time-definite deliveries, which makes
the integration of customer time windows into the routing model a necessity.  The second aspect
is especially interesting as recharging times for BEVs cannot be assumed to be fixed but depend
on the current battery charge of the vehicle when arriving at the recharging station.  Moreover,
recharging operations take a significant amount of time, especially compared to the relatively
short customer service times of SPS companies, and thus clearly affect the route planning.
In this paper, we introduce the Electric Vehicle Routing Problem with Time Windows and
Recharging Stations (E-VRPTW), which incorporates the possibility of recharging at any of the
available stations using an appropriate recharging scheme, i.e., recharging times depend on the
battery charge of the vehicle on arrival at the station.  Moreover, the most important practical
requirements  of  logistics  providers  using  BEVs,  namely  capacity  constraints  on  vehicles  and
customer time windows are included.  E-VRPTW aims at minimizing the number of employed
vehicles and total traveled distance.
As E-VRPTW extends the well-known VRPTW, the high complexity of the problem renders
exact  solution  methods  inadequate  for  solving  realistically  sized  problem  instances  (Baldacci
et al. 2012).  To solve E-VRPTW, we develop a hybrid metaheuristic, which combines a Variable
Neighborhood Search (VNS) heuristic with a Tabu Search (TS) method for the intensification
phase of the VNS. In numerical studies, we prove the quality and efficiency of our VNS/TS on
test instances of related problems, namely the G-VRP and the Multi-Depot VRP with Inter-
Depot Routes (MDVRPI). Moreover, we design two sets of benchmark instances for E-VRPTW:
A set of small-sized instances that we can solve exactly with the optimization software CPLEX
in  order  to  assess  the  performance  of  VNS/TS  on  E-VRPTW  and  a  set  of  more  realistically
sized instances, on which we study the effectiveness of every component of our hybrid solution
method.
The paper is organized as follows.  In Section 2, a review of related literature is presented.  In
Section 3, we introduce the notation in detail and provide a mixed-integer linear programming
formulation  of  E-VRPTW.  Section  4  describes  the  VNS/TS  hybrid  for  solving  E-VRPTW.
Experimental results obtained on newly designed E-VRPTW instances as well as on benchmark
sets  of  related  problems  are  presented  in  Section  5.   Section  6  gives  a  short  summary  and
conclusion of the paper.
## 2

## 2  Literature Review
In this section, we briefly review the literature related to the problem addressed in this paper.
The use of BEVs requires the integration of distance constraints depending on battery charge.
Distance constraints in order to include working hour restrictions by assuming the duration to be
related to route length by an average speed are quite common in VRPs.  Due to the widespread
availability of petrol stations and the large cruising range of gasoline powered vehicles, distance
constraints,  however,  have  scarcely  attracted  interest  as  pure  range  (fuel)  constraints.   Some
works on military issues propose concepts to extend the length of vehicle chains when fuel can
be transferred between vehicles (Mehrez and Stern 1985, Melkman et al. 1986).
E-VRPTW extends the VRPTW, which is probably the most studied VRP variant in the
last two decades.  In the VRPTW, service at a customer has to start within a given time interval,
which is a highly relevant constraint in real-world routing applications (see,  e.g., Br ̈aysy and
Gendreau 2005a). Numerous heuristic solution methods has been proposed to solve the VRPTW.
Among the best performing are the edge-assembly memetic algorithm of Nagata et al. (2010),
the branch-and-price based large neighborhood search of Prescott-Gagnon et al. (2009) and the
reactive VNS of Br ̈aysy (2003).  For state-of-the-art reviews of heuristic and exact methods for
VRPTW, we refer the reader to Gendreau and Tarantilis (2010) and Baldacci et al. (2012).
Another problem that is closely related to E-VRPTW is an extension of the Multi-Depot
VRP (MDVRP) described in Crevier et al. (2007).  The MDVRP itself is a well-known VRP
variant, where vehicles are located at several locally disperse depots and each route has to end
at the depot it originated from.  The extension by Crevier et al. (2007) is called MDVRP with
Inter-Depot Routes (MDVRPI) and is motivated by the deliveries of a grocery in Montreal.  The
model considers intermediate depots at which vehicles can be replenished with goods during the
course of a route.  To solve the MDVRPI, Crevier et al. (2007) present a heuristic procedure that
combines ideas from adaptive memory programming, described in Rochat and Taillard (1995),
TS and integer programming.  More precisely, the problem is split into three subproblems:  an
MDVRP, a VRP and an inter-depot subproblem, for which solutions are determined by means
of a TS heuristic and saved in a solution pool.  The generated routes are subsequently merged by
means of a set-partitioning algorithm, followed by an improvement phase.  Although the multi-
depot case is described, all proposed benchmark instances consider only one depot at which the
vehicle fleet is stationed.
Therefore, Tarantilis et al. (2008) rename the problem to VRP with Intermediate Replenish-
ment Facilities (VRPIRF). They propose a hybrid guided local search heuristic that follows a
three-step procedure.  First, an initial solution is constructed by means of a cost-savings heuris-
tics.   Second,  a  VNS  algorithm  is  applied  using  a  TS  in  the  local  search  phase,  instead  of  a
greedy procedure.  Third, the solution is further improved by means of a guided local search.
In  numerical  tests  performed  on  available  benchmark  instances,  the  heuristic  clearly  outper-
forms the solution procedure proposed by Crevier et al. (2007).  In addition,  they present 54
new benchmark instances with up to 175 customers.  Problems similar to VPRIRF arise in the
collection of waste, for example, described by Kim et al. (2006).  In this context, however, the
objective is not only to minimize travel distance but also to balance the workload among the
vehicles and to obtain a high route compactness.
Relatively few literature has been published on optimization problems related to alternative
fuels.  Most articles deal with the question how to place refueling stations in an infrastructure-
oriented  context,  either  for  refueling  vehicles  using  compressed  natural  gas  (CNG)  (Boostani
et  al.  2010)  or  electricity  (Qiu  et  al.  2011).   The  development  of  an  infrastructure  consisting
of refueling stations, differing in terms of refueling speed and capacity, has been realized to be
crucial for the promotion of AFVs.  The models usually use a node or flow-based set covering
problem  to  determine  the  optimal  number  and  location  of  the  refueling  stations.   To  model
the  fuel  demand  for  short-distance  trips  in  urban  areas,  customers  are  usually  aggregated  to
nodes and a node-based formulation is used.  Considering long-distance trips within the location
## 3

decision, the flow between origin-destination pairs is used as a measure for the demand (Wang
and Lin 2009, Wang and Wang 2010).
Other work concentrates on finding the energy shortest path from a given origin to a desti-
nation, which can, e.g., be used in navigation systems.  Given a battery capacity, the objective
is to maximize the energy level at the destination while positive arcs represent energy consump-
tion and negative arcs recuperation (Artmeier et al. 2010).  Wang and Shen (2007) propose a
scheduling problem for electric buses, called Vehicle Scheduling Problem with Route and Fueling
Time Constraints.  They assign timetabled trips, that are known in advance, to buses with the
objective of minimizing total idle time.  The travel range is limited by the vehicle’s charge so
every vehicle has to be recharged after several trips.
Finally, we are aware of three publications that explicitly consider the specific characteristics
of  alternative  fuels  and  adopt  them  to  VRPs.   Gon ̧calves  et  al.  (2011)  consider  a  VRP  with
Pickup  and  Delivery  (VRPPD)  with  a  mixed  fleet  that  consists  of  BEVs  and  vehicles  using
internal-combustion engines.  The objective is to minimize total costs, which consist of vehicle-
related fixed and variable costs.  They consider time and capacity constraints and assume a time
for recharging the BEVs, which they calculate from the total distance travelled and the range
using one battery charge.  However, they do not incorporate the actual location of recharging
stations into their model.  Thus, they basically propose a mixed-fleet VRPPD with an additional
distance-dependent time variable.
To the best of our knowledge, Erdogan and Miller-Hooks (2012) are the first to combine a
VRP with the possibility of refueling a vehicle at a station along the route.  They are mainly
motivated by vehicle fleets operating on a wide geographical region and driving with biodiesel,
liquid  natural  gas  or  CNG.  For  these  fuels  only  a  limited  refueling  infrastructure  exists,  but
refueling times may be assumed to be fixed.  The proposed G-VRP considers a maximum route
duration and fuel constraint.  Fuel is consumed with a given rate per traveled distance and can
be replenished at AFS. In principle,  the G-VRP is modeled as an extension to the MDVRPI
and Erdogan and Miller-Hooks (2012) propose two heuristics to solve the new problem.  The
first heuristic is a Modified Clarke and Wright Savings algorithm (MCWS) which creates routes
by establishing feasibility through the insertion of AFSs, merging feasible routes according to
savings  and  removing  redundant  AFSs.   The  second  heuristics  is  a  Density-Based  Clustering
Algorithm  (DBCA)  based  on  a  cluster-first  and  route-second  approach.   The  DBCA  forms
clusters of customers such that every vertex within a given radius contains at least a predefined
number of neighbors.  Subsequently, the MCWS algorithm is applied on the identified clusters.
For the numerical studies, Erdogan and Miller-Hooks (2012) design two sets of problem instances.
The  first  consists  of  40  small-sized  instances  with  20  customers  and  the  second  involves  12
instances with up to 500 customers.
3  The Electric Vehicle Routing Problem with Recharging Sta-
tions and Time Windows (E-VRPTW)
LetVbe a set of vertices withV=I∪F
## ′
, whereIdenotes the set of customers andF
## ′
a set
of dummy vertices generated to permit several visits to each vertex in the setFof recharging
stations.  Further, letv
## 0
andv
n+1
denote instances of the same depot, where every route starts
atv
## 0
and ends atv
n+1
and let the indices 0 andn+ 1 indicate that a set contains the respective
instance  of  the  depot,  e.g.,V
## 0
=V∪{v
## 0
}.   Then  E-VRPTW  can  be  defined  on  a  complete
directed graphG= (V
## 0,n+1
,A),  with the set of arcsA={(i,j)|i,j∈V
## 0,n+1
## ,i6=j}.  With
each arc,  a distanced
ij
and a travel timet
ij
are associated.  Each traveled arc consumes the
amountr·d
ij
of the remaining battery charge of the vehicle traveling the arc, whererdenotes
the constant charge consumption rate.
At the depot, a set of homogeneous vehicles with a maximal capacity ofCare positioned.
Each vertexi∈V
## 0,n+1
is assigned a positive demandq
i
, which is set to 0 ifi6∈I.  Moreover,
## 4

each  vertexi∈V
## 0,n+1
has  a  time  window  [e
i
## ,l
i
]  and  all  customersj∈Ihave  an  associated
service  times
j
.   Service  cannot  begin  beforee
i
,  which  might  cause  waiting  time,  and  is  not
allowed to start afterl
i
but might end later.  At a recharging station, the difference between the
present charge level and the battery capacityQis recharged with a recharging rate ofg, i.e., the
recharging time incurred depends on the fuel level of the vehicle when arriving at the respective
station.
Instead of a three-index formulation,  we use decision variables associated with vertices to
keep  track  of  vehicle  states,  thus  keeping  the  number  of  required  variables  low.   Variableτ
j
specifies the time of arrival,u
j
the remaining cargo andy
j
the remaining charge level on arrival
at vertexj∈V
## 0,n+1
.  The decision variablesx
ij
|i∈V
## 0
,j∈V
n+1
,i6=jare binary and equal 1
if an arc is traveled and 0 otherwise.
The objective function of E-VRPTW is hierarchical.  As commonly done for vehicle routing
problems with time window constraints (see, e.g., Br ̈aysy and Gendreau 2005b), our first objec-
tive is to minimize the number of vehicles, i.e., a solution with less vehicles is always superior.
The second objective is to minimize the total traveled distance.
The mathematical model of E-VRPTW is formulated as mixed-integer program as follows:
min
## ∑
i∈V
## 0
,j∈V
n+1
## ,i6=j
d
ij
x
ij
## (1)
## ∑
j∈V
n+1
## ,i6=j
x
ij
= 1∀i∈I(2)
## ∑
j∈V
n+1
## ,i6=j
x
ij
≤1∀i∈F
## ′
## (3)
## ∑
i∈V
n+1
## ,i6=j
x
ji
## −
## ∑
i∈V
## 0
## ,i6=j
x
ij
= 0∀j∈V(4)
τ
i
## + (t
ij
## +s
i
## )x
ij
## −l
## 0
## (1−x
ij
## )≤τ
j
∀i∈I
## 0
,∀j∈V
n+1
## ,i6=j(5)
τ
i
## +t
ij
x
ij
+g(Q−y
i
## )−(l
## 0
+gQ)(1−x
ij
## )≤τ
j
∀i∈F
## ′
,∀j∈V
n+1
## ,i6=j(6)
e
j
## ≤τ
j
## ≤l
j
∀j∈V
## 0,n+1
## (7)
## 0≤u
j
## ≤u
i
## −q
i
x
ij
+C(1−x
ij
)∀i∈V
## 0
,∀j∈V
n+1
## ,i6=j(8)
## 0≤u
## 0
## ≤C(9)
## 0≤y
j
## ≤y
i
## −(r·d
ij
## )x
ij
+Q(1−x
ij
)∀j∈V
n+1
,∀i∈I,i6=j(10)
## 0≤y
j
≤Q−(r·d
ij
## )x
ij
∀j∈V
n+1
,∀i∈F
## ′
## 0
## ,i6=j(11)
x
ij
∈{0,1} ∀i∈V
## 0
,j∈V
n+1
## ,i6=j(12)
The objective function is defined in (1).  Constraints (2) enforce the connectivity of costumers
and  Constraints  (3)  handle  the  connectivity  of  visits  to  recharging  station.   Constraints  (4)
establish flow conservation by guaranteeing that at each vertex, the number of incoming arcs
is  equal  to  the  number  of  outgoing  arcs.   Constraints  (5)  guarantee  time  feasibility  for  arcs
leaving customers and the depot, Constraints (6) do the same for arcs leaving recharging visits.
As mentioned above,  recharge times are for a complete recharge with rategfrom the charge
levely
i
on arrival up to the maximum battery capacityQ.  Constraints (7) ensure that every
vertex is visited within its time window.  Further, Constraints (5) - (7) prevent the formation of
subtours.  Constraints (8) and (9) guarantee demand fulfillment at all customers by assuring a
non-negative cargo load upon arrival at any vertex.  Finally, Constraints (10) and (11) ensure
that the battery charge never falls below zero.
4  A Hybrid VNS/TS Solution Method for the E-VRPTW
As solution method for E-VRPTW, we use a combination of VNS and TS, a hybrid that has
already proven its performance on routing and related problems (see, e.g., Melechovsky et al.
## 5

## 1:N
κ
←set of VNS neighborhood structures forκ= 1,...,κ
max
2: Generate initial solutionS
## 3:κ←1
## 4:i←0
5: feasibilityPhase←true
6:whilefeasibilityPhase∨(¬feasibilityPhase∧i < η
dist
## )do
## 7:S
## ′
←random point∈N
κ
## (S))
## 8:S
## ′′
←best solution afterη
tabu
iterations of tabu search withS
## ′
as initial solution
9:ifacceptSA(S
## ′′
,S)then
## 10:S←S
## ′′
## 11:κ←1
## 12:else
## 13:κ←κ+ 1
14:end if
15:iffeasibilityPhasethen
16:if¬feasible(S)then
## 17:ifi=η
feas
then
18:addVehicle(S)
## 19:i←−1
20:end if
## 21:else
22:feasibilityPhase←false
## 23:i←−1
24:end if
25:end if
## 26:i←i+ 1
27:end while
Figure 1:  Overview of our VNS/TS algorithm for solving E-VRPTW.
2005, Tarantilis et al. 2008).  VNS, proposed by Mladenovi ́c and Hansen (1997), is an effective
metaheuristic performing local search on increasingly larger neighborhoods in order to efficiently
explore the solution space and to avoid getting stuck in local optima.  It has successfully been
applied to a variety of combinatorial optimization problems, among them routing problems like
VRPTW with single or multiple depots (Br ̈aysy 2003, Polacek et al. 2004).
TS is a powerful metaheuristic, which guides local search heuristics to search a solution space
economically and effectively (Glover and Laguna 1997).  Starting from an initial solution, the
best non-tabu move is conducted at each iteration.  The diversification of the search is obtained
by  integrating  a  memory  structure  called  tabu  list,  which  prevents  the  search  heuristic  from
cycling.  TS methods have provided near-optimal solution qualities and proved their efficiency
for many combinatorial optimization problems (Gendreau and Potvin 2010).
Figure 1 presents our solution method in pseudocode.  After a preprocessing step removing
infeasible arcs, we generate an initial solutionSwith a given number of vehicles as described
in  Section  4.1.   Infeasible  solutions  are  allowed  during  the  search  and  evaluated  based  on  a
penalizing cost function (see Section 4.2).  We first perform a feasibility phase during which the
number  of  vehicles  is  increased  after  no  feasible  solution  has  been  found  for  a  given  number
ofη
feas
iterations.  After a feasible solution is found, anotherη
dist
iterations are performed to
improve traveled distance.
The  search  is  guided  by  a  VNS  component  described  in  Section  4.3.   It  uses  the  current
VNS neighborhoodN
κ
to generate a random perturbation which serves as initial solution for
η
tabu
iterations of the TS phase (Section 4.4).  The acceptance criterion of the VNS is based on
Simulated Annealing (SA).
4.1  Preprocessing and Generation of Initial Solution
As commonly done, we apply a preprocessing step to remove infeasible arcs (see, e.g., Psaraftis
1983, Savelsbergh 1985).  Arc (v,w) connecting verticesvandwcan be removed from the set
## 6

of possible arcs if one of the following inequalities holds:
q
v
## +q
w
≥C∀v,w∈I(13)
e
v
## +s
v
## +t
vw
## ≥l
w
∀v∈V
## 0
,∀w∈V
n+1
## (14)
e
v
## +s
v
## +t
vw
## +s
w
## +t
wn+1
## ≥l
## 0
∀v∈V
## 0
,w∈V(15)
r(d
jv
## +d
vw
## +d
wi
)≥Q∀v,j∈V
## 0
,∀w,i∈V
n+1
## (16)
Equation  (13)  -  (15)  are  well-known  preprocessing  steps  that  base  on  capacity  and  time
window  violations.   Equation  (16)  is  problem-specific  and  refers  to  violations  of  the  battery
capacity.  If the charge consumption of traveling an arc and traveling to and from that arc to
any station or the depot is higher than the battery capacity, this arc can be labelled infeasible.
Numerical studies showed that this preprocessing step is able to strongly reduce the number of
feasible arcs on our E-VRPTW test instances.
We construct an initial solution similar to the approach proposed in Cordeau et al. (2001).
First, all customers are sorted in increasing order of the angle between the depot, a randomly
chosen point and the customer.  Then, customers are iteratively inserted into the active route at
the position causing minimal increase in traveled distance until a violation of capacity or battery
capacity  occurs.   If  a  violation  occurs,  we  activate  a  new  route  until  at  most  the  predefined
number of routes are opened. The battery capacity violation is determined under the assumption
that no recharging possibility exists.  To consider time window requirements,  a customeruis
only allowed to be inserted between successive verticesi,jife
i
## ≤e
u
## ≤e
j
.  This rule helps to
keep time windows but feasibility is only guaranteed concerning capacity and battery capacity
for all routes but the last.
## 4.2  Generalized Cost Function
As  commonly  done  in  literature,  our  solution  methods  allows  infeasible  solutions  during  the
search process.  A solution is evaluated by means of the following generalized cost function:
F(S) =L(S) +αP
cap
(S) +βP
tw
(S) +γP
batt
## (S) +P
div
## (S),(17)
whereL(S) denote the total traveled distance,P
cap
(S) the total capacity violation,P
tw
## (S)
the  time  window  violation,P
batt
(S)  the  battery  capacity  violation,P
div
(S)  a  diversification
penalty andα,βandγare factors weighting the violations.  The penalty factors are dynamically
updated between a given lower and upper bound.  In order to balance between diversification
and  intensification,  they  are  increased  by  a  factorδafter  the  respective  constraint  has  been
violated  for  a  certain  number  of  iterations  and  divided  byδif  the  respective  constraint  was
satisfied.
In the following,  we describe the efficient calculation of the constraint violations.  Let the
sequencev(k) =〈v
## 0
## ,v
## 1
## ,...,v
n
## ,v
n+1
〉contain all ordered vertices of routek.  Then, the capacity
violation of routekcan be calculated as
## P
cap
(k) = max{
## ∑
i∈v(k)
d
i
## −C,0},
wherev(k) refers to the set of customers in routek.  The total capacity penalty of a solutionS
is calculated by adding the individual violations of all routesm:
## P
cap
## (S) =
m
## ∑
k=1
## P
cap
## (k)
By saving forward and backward capacity requirements for each vertex (see, e.g., Kindervater
and  Savelsbergh  1997,  Ibaraki  et  al.  2005),  we  are  able  to  calculate  the  change  in  capacity
## 7

violation  in  constant  timeO(1)  for  all  neighborhood  operators  of  our  TS  method,  which  are
introduced in Section 4.4.
To calculate battery capacity violations, we define the following two variables:  Υ
## →
v
i
contains
the  battery  charge  that  is  needed  to  travel  from  the  last  visit  to  a  recharging  station  or  the
depot to vertexv
i
and Υ
## ←
v
i
is the battery charge that is needed fromv
i
to the next recharging
station or the depot:
## Υ
## →
v
i
## =
## {
r·d
v
i−1
v
i
ifv
i−1
## ∈F
## ′
## 0
## Υ
## →
v
i−1
## +r·d
v
i−1
v
i
otherwise
## (i= 1,...,n+ 1)
## Υ
## ←
v
i
## =
## {
r·d
v
i
v
i+1
ifv
i+1
## ∈F
## ′
n+1
## Υ
## ←
v
i+1
## +r·d
v
i
v
i+1
otherwise
## (i= 0,...,n)
The  battery  capacity  violation  of  a  routekcan  then  be  calculated  by  adding  the  individual
violations at every visit to a recharging station and on return to the depot:
## P
batt
## (k) =
## ∑
v
i
∈v(k)∩F
## ′
n+1
max{Υ
## →
v
i
## −Q,0}
Using the presented variables, changes in battery capacity violation can be calculated inO(1)
for all of the neighborhood operators described in Section 4.4.
To calculate time window violations, we adapt the time window handling approach described
in Nagata et al. (2010) and enhanced by Schneider et al. (2012) to E-VRPTW. The approach
bases on the notion of time travel, i.e., the calculation of the violation at a customer that follows
a customer with a time window violation is executed as if a travel back in time to the latest
feasible arrival time at the preceding (violating) customer had taken place.  By putting a penalty
only on the first vertex where a time window is violated instead of propagating the violation
along the entire route,  the approach avoids penalizing good customer sequences only because
they  occur  after  a  time  window  violation.   Another  important  advantage  of  the  approach  is
that potential time window violations for inter-route moves can be calculated inO(1) for most
classical neighborhood structures.
More precisely, by storing forward and backward time window penalty slacks, it is possible
to calculate in constant time the time window penalties of a routek
## 1
=〈0,...,u,w,...,0〉that is
constructed from two partial routes〈0,...,u〉and〈w,...,0〉or of a routek
## 2
## =〈0,...,u,v,w,...,0〉
that is constructed by inserting a vertexvbetween two partial routes〈0,...,u〉and〈w,...,0〉.
This is not always possible if recharging stations are present as the recharging time at a station
depends on the battery charge, which itself depends on the traveled distance to the recharging
station.  If the partial route〈w,...,0〉contains a recharging stationθ, i.e.,〈w,..,θ,θ+ 1,..,0〉,
slack variables have to be recalculated by traversing the partial route〈w,..,θ+ 1〉fork
## 1
and the
partial route〈v,..,θ+ 1〉fork
## 2
.  Note that a recharging station in the first partial route〈0,...,u〉
or the vertex to insertvbeing a recharging station does not necessitate a recalculation.
## 4.3  The Variable Neighborhood Search Component
Within our hybrid VNS/TS heuristic, the VNS component is mainly used to diversify the search
in a structured way.  To explain the functionality of our VNS, we first briefly sketch a standard
VNS procedure.  Subsequently, we detail the specific characteristics of our implementation.
A general VNS algorithm works as follows: Given a predefined set of neighborhood structures
and  the  current  best  solutionS,  VNS  randomly  generates  a  neighboring  solutionS
## ′
in  the
shaking  phase  by  means  of  the  neighborhood  structureN
κ
.   Next,  a  greedy  local  search  is
applied onS
## ′
to determine the local minimumS
## ′′
.  IfS
## ′′
improves on the current best solution
S, the VNS algorithm accepts the solutionS
## ′′
and restarts with neighborhoodN
## 1
and the new
starting solutionS
## ′′
.  By contrast, ifS
## ′′
is worse than the incumbent best solution,S
## ′′
is refused.
## 8

In  this  case,  VNS  performs  a  random  perturbation  move  according  to  the  next  more  distant
neighborhood structureN
κ+1
, starting again withS.
In our hybrid VNS/TS algorithm, the shaking phase is equal to the standard VNS approach,
but the intensification phase as well as the acceptance criterion clearly differs.  In the following,
we detail the shaking phase, the local search phase and the acceptance criterion used in the VNS
component of our hybrid heuristic.
In every iteration our VNS performs a random perturbation move according to the prede-
fined neighborhood structureN
κ
.  Our neighborhood structures are all defined by means of the
cyclic-exchange operator.  In the cyclic-exchange,  introduced by Thompson and Orlin (1989),
Thompson and Psaraftis (1993), customer sequences of arbitrary length are simultaneously trans-
ferred between routes.  Ourκneighborhood structures, shown in Table 1, are defined according
to the following parameters:  The number of routes which built the cycle is equal to #Rts.  In
each routek, we randomly select the number of successive vertices that form the translocation
chain in the interval [0,min{Γ
max
## ,n
k
}], wheren
k
denotes the number of customers and stations
contained ink.  The initial vertex of a chain is randomly chosen in each route.  Cyclic-exchange,
κ#RtsΓ
max
κ#RtsΓ
max
κ#RtsΓ
max
## 1216311141
## 2227321242
## 323
## 8331343
## 424
## 9341444
## 52510351545
Table 1:  Theκ-neighborhood structures used in the VNS defined by the number of involved
route #Rtsand the maximum number of translocated vertices Γ
max
## .
or a variant that is restricted to two routes, called cross-exchange, are commonly used in the
perturbation phase of VNS-algorithms (see, e.g, Polacek et al. 2004, Hemmelmayr et al. 2009).
In the local search phase, we improve the randomly generated solutionS
## ′
by means of our
TS  heuristic,  detailed  in  Section  4.4.   The  search  stops  afterη
tabu
iterations.   Note  that  the
perturbation move is added to the general tabu list to prevent its reversal.  Subsequently,  we
compare the best solution found during the local searchS
## ′′
to the initial solutionS.  Instead
of  accepting  only  improving  solutions,  we  use  an  acceptance  criterion  that  is  inspired  by  the
metaheuristic SA (Kirkpatrick et al. 1983).  This method has been successfully applied in several
VNS approaches, for example, in Hemmelmayr et al. (2009) and Stenger et al. (2011).
To be more precise, improving solutions are always accepted, while we accept deteriorating
solutions according to the Metropolis probability.  Letf(·) denote the objective function value,
the probability of accepting solutionS
## ′′
is calculated bye
−(f(S
## ′′
)−f(S))
θ
.  Variableθis a system
parameter,  that  is  called  temperature.   At  the  beginning  of  the  search,  the  temperature  is
usually initialized to a high valueθ
init
, so that deteriorating solutions are often accepted, which
helps to diversify the search.  By continuously decreasing the temperature during the search, an
intensification is achieved and, finally, only improving solutions are accepted.  In our case, we
setθ
init
in a way that a solution valuef(S
## ′′
), which isw
## SA
worse thanf(S) is accepted with
a probability of 50%.  After every VNS iteration, the temperature is linearly decreased with a
cooling factorwhich is chosen such that the temperature is below 0.0001 during the last 20%
of iterations.
## 4.4  The Tabu Search Component
The  TS  phase  starts  from  the  solutionS
## ′
generated  by  the  perturbation  move  of  the  VNS
component.  In each iteration, the composite neighborhoodN(S) of TS is generated by applying
the following neighborhood operators on every arc in the list of generator arcs (cp. Toth and
Vigo 2003):  2-opt*, relocate, exchange and a new, problem-specific operator called stationInRe.
Each move is evaluated and the best non-tabu move is performed.  A move is superior if it is
## 9

able to reduce the number of employed vehicles or if it has a lower cost function value calculated
with Equation (17).
The  2-opt*  operator  is  a  modification  of  the  2-opt  operator  originally  introduced  in  Lin
(1965) and was specifically proposed for the VRPTW by Potvin and Rousseau (1995).  It avoids
the reversal of route directions by removing one arc from each route and reconnecting the first
part  of  the  first  route  with  the  second  part  of  the  second  route  and  vice  versa.   We  apply
2-opt*  for  inter-route  moves  and  define  the  operator  for  moving  recharging  stations,  i.e.,  we
allow  the  removal  and  insertion  of  arcs  including  recharging  stations.   The  relocate  operator
was introduced in Savelsbergh (1992) and removes one vertex from a route and inserts it into
another route or a different position in the same route.  Relocate is also defined for recharging
station and applied as intra- and inter-route operator.  The exchange operator, also introduced
in Savelsbergh (1992), swaps the position of two vertices.  The operator is applied for inter-route
and intra-route moves, but is not defined for recharging stations, i.e., we exclude the swapping
of a recharging station with a customer or another station.
As the name suggests, the stationInRe operator performs insertions and removals of recharg-
ing  stations.   The  operator  is  defined  for  all  generator  arcs  (v,w),  where  eithervorwis  a
recharging station.  Letw
## −
denote the predecessor of vertexw.  If the arc (v,w) is not part of
the current solution, stationInRe performs an insertion as depicted in Figure 2(a).  If the arc is
already present, a recharging station is removed as shown in 2(b).
w
## -
w
v
## (a) Insertion
w
## -
w
v
## (b) Removal
Figure 2: Insertion and removal of a recharging station with the stationInRe operator. Generator
arcs are shown in bold and removed arcs as dashed lines.
We set every arcξthat is deleted from the solution by the execution of a move tabu, i.e, we
forbid the reinsertion of the arc into the solution for a specified number of iterations called tabu
tenure.  As station visits have a strong effect on charge levels and also on time windows due to
recharging times incurred, we define the tabu attribute (ξ,k,μ,ζ).  It prohibits the insertion of
arcξinto routekbetweenμandζ, whereμ,ζ∈F
## 0,n+1
denote either a station or the depot.  In
this way, we allow the reinsertion of an arc into a different part of the route.  The tabu tenure
for each arc is randomly drawn from the the interval [ρ
min
## ,ρ
max
].  The tabu status of a move
can be lifted if a so-called aspiration criterion is met, in our case if a feasible new best solution
is generated.
To  further  diversify  the  search,  we  adapt  the  continuous  diversification  mechanism  pre-
sented in Cordeau et al. (2001) to E-VRPTW. Using the notation introduced above, we define
vertex-based  attributes  (u,k,μ,ζ)  to  describe  that  customer/stationuis  positioned  between
stations/depotμandζin routek.  In this way,  each solutionScan be characterized by the
attribute setB
vertex
(S) ={(u,k,μ,ζ)}.  For each attribute, the frequencyp
ukμζ
of its addition
to a solution in previous moves is memorized and used to penalize solutions according to the
frequency  of  their  attributes.   Thus,  we  guide  the  search  to  explore  the  possibilities  of  using
different stations and different positions of customers and stations (relative to other stations or
the depot) within a route.  A solutionS, which does not improve the overall best solution, is
penalized by:
## P
div
(S) =λL(S)
## √
nm
## ∑
(u,k,μ,ζ)∈B
vertex
## (S)
p
ukμζ
## ,
whereλis a parameter to control the amount of diversification and the scaling factorL(S)
## √
nm
establishes  a  relation  between  the  diversification  penalty  and  the  traveled  distance  and  the
## 10

investigated problem size withncustomers andmvehicles.  The TS procedure is stopped after
η
tabu
iterations.
## 5  Numerical Experiments
In this section, we present the extensive numerical testing conducted to evaluate the performance
of our hybrid VNS/TS method.  The first study evaluates the performance of our VNS/TS on
E-VRPTW  instances.   To  be  able  to  asses  the  solution  quality,  we  use  newly  designed  small
instances which can be solved by means of the commercial solver CPLEX. In our second study,
we  analyze  the  efficiency  of  the  algorithmic  components  of  our  hybrid  heuristics,  namely  the
VNS, TS and SA, on a set of medium-sized E-VRPTW instances, which we designed based on
classical Solomon VRPTW instances.  Finally, we demonstrate the strong performance concern-
ing solution quality and runtime of our VNS/TS on available benchmark instances of the related
problems MDVRPI and G-VRP.
The section is structured as follows.  After a brief discussion of the chosen parameter setting
in Section 5.1, we describe the tests performed on E-VRPTW benchmark instances in Section
5.2 and those performed on benchmark instances of related problems in Section 5.3.
## 5.1  Experimental Environment & Parameter Settings
All tests are performed on a desktop computer equipped with an Intel Core i5 processor with
2.67 GHz and 4 GB RAM, operating Windows 7 Professional.  The VNS/TS is implemented as
single-thread code in java.  The parameters we used to generate the final results are provided in
Table 2.  The presented values are the result of intensive studies we conducted to fine-tune our
algorithm.  In the following, we briefly discuss only those parameters that have a strong effect
on the performance of our algorithm.
## Phases
PenaltiesTabu listConti.  Div.VNS
η
feas
## 500α
## 0
## ,β
## 0
## ,γ
## 0
## 10ρ
min
## 15λ1.0η
tabu
## 100
η
dist
## 200α
min
## ,β
min
## ,γ
min
## 0.5ρ
max
## 30w
## SA
## 8%
α
max
## ,β
max
## ,γ
max
## 5000
δ1.2
η
penalty
## 2
Table 2:  Overview of the parameter settings chosen for the numerical studies.
During our testing, we observed that the values chosen for the initial penalty factorsα
## 0
## ,β
## 0
## ,γ
## 0
are crucial for the solution quality of our VNS/TS. In case of high values, the search often got
stuck in low-quality local minima and required several iterations before continuing an effective
search of solution space.  By contrast, setting the initial value too low favors the acceptance of
highly infeasible solutions, which also has a negative influence on the performance.  We obtained
best  results  with  a  value  of  10,  which  seems  a  good  compromise  between  diversification  and
intensification at the beginning of the search.  During the search, the penalty factors are updated
by multiplying or dividing by factor 1.2, while limiting the values to the interval [0.5,5000].
Concerning the feasibility phase, the tests showed that if the VNS/TS is not able to find a
feasible solution with the given number of vehicles in 500 VNS iterations, it is very unlikely that
a feasible solution with this vehicle number is found in later iterations.  The entire algorithm
terminates after 200 additional distance minimization iterations as this resulted in a good trade-
off between computing time and solution quality.  Furthermore, the length of the tabu list clearly
affected the performance of our algorithm.  However, we were not able to find a unique value
that performed well on all instances of the different benchmark sets that we solved.  Instead, we
achieved the overall best results by randomly selecting the length from the interval [15,30] in
each iteration.
## 11

5.2  Experiments on E-VRPTW Instances
As we are the first to study E-VRPTW, no benchmark instances for assessing solution methods
for this problem exist.  We design two new sets of benchmark instances, which we describe in
Section 5.2.1.  Section 5.2.2 presents the results of our testing on the generated instances.
5.2.1    Generation of E-VRPTW Benchmark Instances
We create two sets of benchmark instances for the E-VRPTW. A set of 56 large instances, each
with 100 customers and 21 recharging stations, and a set of 36 small instances with 5, 10 and
15 customer per instance.  All instances are created based on the benchmark instances for the
VRPTW  proposed  by  Solomon  (1987).   These  instances  are  divided  into  3  classes  depending
on the geographical distribution of the customer locations:  Random customer distribution (R),
clustered  customer  distribution  (C)  and  a  mixture  of  both  (RC).  Groups  R1,  C1  and  RC1
have a short scheduling horizon, meaning that generally more vehicles are required to serve all
customers than in R2, C2 and RC2, which have a long scheduling horizon.  The instances within
a group differ in terms of time window density and time window width.  In the following, we
detail the design of the large E-VRPTW instances based on the described VRPTW instances.
Given an original Solomon instance, we first determine the locations of the recharging sta-
tions.   We  locate  one  recharging  station  at  the  depot  because  a  recharging  possibility  at  the
depot seems to be a reasonable claim.  The location of the remaining 20 stations is determined
in a random manner.  However, we limit the possible locations such that the feasibility of the
instance is guaranteed, i.e., that every customer can be reached from the depot using at most
two different recharging stations.
The battery capacity is set to the maximum of the following two values: 1) 60% of the average
route length of the best known solution to the corresponding VRPTW instance and 2) twice the
amount of battery charge required to travel the longest arc between a customer and a station.
This procedure ensures that instances with geographically disperse and remote customers stay
feasible  and,  on  the  other  hand,  allows  the  formation  of  reasonable  routes  in  instances  with
closely located customers.  Furthermore, we thus guarantee that recharging stations have to be
used.  For the sake of simplicity, we set the consumption rate to 1.0.  The inverse refueling rate
is set to a value so that a complete refueling requires three times the average customer service
time of the respective instance.
Since the limited battery capacity and the need for recharging along the routes lead to longer
route durations,  the customer time windows given in the original VRPTW instances have to
be  altered,  as  instances  with  tight  time  windows  would  otherwise  become  infeasible.   To  this
end,  we  determine  new  time  windows  following  the  procedure  described  in  Solomon  (1987).
For  a  detailed  description  of  our  instance  design,  we  refer  the  reader  to  the  following  URL:
http://evrptw.wiwi.uni-frankfurt.de, where the generated instances are also available for
download.
To generate the set of small instances, we first generate 168 instances of three sizes (5,10,15
customers)  by  randomly  drawing  the  respective  number  of  customer  from  each  of  the  large
instances.  The created instances are solved with our VNS/TS heuristic and the solutions are
inspected.  For each problem group and instance size, we select the two instances whose solution
uses the highest number of recharging stations.  In this way, we create 6·3·2 = 36 small test
instances.
5.2.2    Performance of VNS/TS on Small E-VRPTW Instances
We  use  the  generated  E-VRPTW  test  instances  to  analyze  the  performance  of  our  VNS/TS
heuristic on small E-VRPTW instances.  To this end, we solve the instances with VNS/TS and
compare the obtained results to the optimal (or near optimal) solution found by the commercial
solver  ILOG  CPLEX  12.2,  using  the  E-VRPTW  formulation  presented  in  Section  3.   Table
## 12

3  provides  an  overview  of  the  results.   For  both,  CPLEX  and  our  heuristic,  we  provide  the
number of vehicles required in columnmand the computing time in seconds in columnt(s).
For the solutions obtained with CPLEX, the objective function value given in columnL
best
## (S)
corresponds to the optimal solution, or the best upper bound found within 7200 seconds.  For
VNS/TS, this column provides the best solution found in 10 runs and column ∆ denotes the
gap to the solution found by CPLEX.
## CPLEXVNS/TS
m  L
best
(S)t(sec)m  L
best
## (S)∆
best
## (%)t(sec)
## C101C52257.75812257.750.000.21
## C103C51176.0551176.050.000.12
## C206C51242.565181242.550.000.14
## C208C5
## 1158.48151158.480.000.11
## R104C52136.6912136.690.000.13
## R105C5
## 2156.0832156.080.000.11
## R202C51128.7811128.780.000.11
## R203C51179.0651179.060.000.15
## RC105C52241.37642241.30.000.14
## RC108C51253.933112253.930.000.17
## RC204C5
## 1176.39541176.390.000.15
## RC208C51167.98211167.980.000.13
## C101C103393.761713393.760.000.77
## C104C10
## 2273.933602273.930.000.95
## C202C101304.063001304.060.000.71
## C205C102228.2842228.280.000.49
## R102C10
## 3249.193893249.190.000.65
## R103C102207.051192207.050.000.72
## R201C101241.511771241.510.000.78
## R203C10
## 1218.215731218.210.000.71
## RC102C104423.518104423.510.000.69
## RC108C103345.93393345.930.000.9
## RC201C101412.8672001412.860.000.9
## RC205C102325.983992325.980.000.81
## C103C153384.2972003384.290.0015.37
## C106C15
## 3275.13173275.130.0014.94
## C202C152383.6272002383.610.0013.41
## C208C152300.5550602300.550.0011.08
## R102C155413.9372005413.930.0019.55
## R105C154336.1572004336.150.0013.35
## R202C152358720023580.0013.17
## R209C151313.2472001313.240.0013.73
## RC103C15
## 4397.6772004397.670.0014.62
## RC108C153370.2572003370.250.0012.92
## RC202C152394.3972002394.390.0012.74
## RC204C151407.4572001384.86-5.8715.57
## Average2483.25-0.165.03
Table 3: Comparison of results obtained with CPLEX and VNS/TS on the small-sized instances.
## L
best
(S) denotes the best found solution with the minimal number of vehiclesm.t(s) denotes the
total runtime in seconds.  The maximum duration for CPLEX was set to 2 hours, so optimality
is not guaranteed for CPLEX results which used the full time.
The  results  clearly  show  the  ability  of  our  VNS/TS  heuristic  to  solve  small  E-VRPTW
instances  to  optimality  in  only  a  few  seconds.   Independent  of  the  instance  structure  or  size,
we always obtain the optimal solution, if CPLEX found an optimum within 7200s.  For most
of  the  15-customer  instances  and  one  10-customer  instance,  CPLEX  was  not  able  to  provide
the optimal solution.  On those instances, we either found a solution equal to the upper bound
provided by CPLEX or a better solution in one case.
5.2.3    Analyzing the Effect of the VNS/TS components
This section aims at demonstrating the positive effect achieved by the hybridization of VNS and
TS. To this end, we compare the results obtained by our VNS/TS heuristic on the 100-customer
instances to the solutions found with 1) a VNS/TS heuristic that accepts only improving solution
after the local search phase instead of using an SA-based criterion (VNS/TS w/o SA) and 2) a
pure TS heuristic.
An overview of the results is given in Table 4.  For each heuristic, we provide the best solution
found in 10 runs (L
best
(S)) and the numbermof required vehicles.  Furthermore, we determine
gaps to the best solution found during the overall testing (BKS) for both the objective function
## 13

value (∆L) and the number of vehicles (∆m).  Finally, at the bottom of the table, the average
computing time in minutes is reported in rowt(min).
BKSVNS/TSVNS/TS w/o SATS
## Instancem L
best
(S)m L
best
## (S)   ∆
m
## ∆
## L
## (%)m L
best
## (S)   ∆
m
## ∆
## L
## (%)m L
best
## (S)   ∆
m
## ∆
## L
## (%)
c10112    1053.8312    1053.8300.0012    1053.8300.0012    1053.8300.00
c10211    1056.4711    1057.1600.0711    1056.4700.0011    1069.3501.22
c103
## 10    1041.5510    1041.5500.0011    1002.031-3.7910    1134.3608.91
c10410979.5110980.8200.1310988.7700.9510979.6300.01
c105
## 11    1075.3711    1075.3700.0011    1075.3700.0011    1079.6900.40
c106
## 11    1057.8711    1057.8700.0011    1057.8700.0011    1057.8700.00
c107
## 11    1031.5611    1031.5600.0011    1031.5600.0011    1033.0800.15
c10810    1100.3210    1100.3200.0011    1015.731-7.6911    1015.731-7.69
c10910    1036.6410    1051.8401.4710    1036.6400.0010    1051.3601.42
c201
## 4645.164645.1600.004645.1600.004645.1600.00
c2024645.164645.1600.004645.1600.004645.1600.00
c2034644.984644.9800.004644.9800.004644.9800.00
c2044636.434636.4300.004636.4300.004636.4300.00
c205
## 4641.134641.1300.004641.1300.004641.1300.00
c2064638.174638.1700.004638.1700.004638.1700.00
c2074638.174638.1700.004638.1700.004638.1700.00
c208
## 4638.174638.1700.004638.1700.004638.1700.00
r101181670.818    1672.5500.1018    1673.1200.14181670.800.00
r10216    1495.3116    1535.8102.7116    1522.8401.8416    1495.3100.00
r103
## 13    1299.1713    1299.6400.0413    1299.1700.0013    1348.2503.78
r10411    1088.4311    1088.4300.0011    1143.6905.0811    1097.0900.80
r10514    1461.2514    1473.5900.8415    1401.241-4.1114    1514.3603.63
r106
## 13    1344.6613    1344.6600.0013    1395.1803.7613    1369.5501.85
r107
## 12    1154.5212    1154.5200.0012    1158.1300.31121162.900.73
r108
## 11    1050.0411    1065.8901.5111    1061.9101.1311    1056.8400.65
r10912    1294.0512    1294.0500.0012    1341.0103.6312    1308.6201.13
r110
## 11    1126.7411    1143.5201.49111141.901.3511    1126.7400.00
r11112    1106.1912    1124.0601.6212    1107.5200.1212    1123.9601.61
r11211    1026.5211    1026.5200.0011    1033.9700.7311    1047.9202.08
r20131264.8231264.8200.0031264.8200.0031266.2600.11
r20231052.3231052.3200.0031053.1100.0831052.6500.03
r2033895.913912.8601.893914.6802.103914.102.03
r2042790.572790.5700.002801.5601.392790.6800.01
r205
## 3988.673988.6700.0031000.9601.243997.1500.86
r2063925.23925.200.003926.9400.193928.2600.33
r2072848.532852.7300.492848.5300.002855.9900.88
r2082736.62736.600.002737.0500.062741.4400.66
r2093872.363872.3600.003877.400.583874.7400.27
r2103847.063847.0600.003850.4100.393848.4400.16
r2112847.452866.2102.212860.3201.522861.1701.62
rc10116    1731.0716    1731.0700.0016    1766.4402.0416    1753.3501.29
rc10215    1554.6115    1554.6100.0015    1556.0800.0915    1559.9500.34
rc10313    1351.1513    1353.5500.1813    1351.1500.0013    1355.3600.31
rc10411    1238.5611    1249.2300.8611    1267.5502.3411    1280.8203.41
rc10514    1475.3114    1483.3800.5514    1475.3100.0014    1479.5600.29
rc10613    1437.9613    1440.1900.1513    1469.9902.2313    1437.9600.00
rc107
## 12    1279.0812    1275.8900.0012    1280.4400.3612    1284.4700.67
rc10811    1209.6111    1238.8102.4111    1227.8801.5111    1209.6100.00
rc20141444.9441447.200.1641444.9400.0041446.0300.08
rc20231418.7931412.9100.0031418.7900.4231425.1700.87
rc20331073.9831078.2800.4031077.1600.3031084.6600.99
rc2043885.353889.2200.443886.0300.083889.2200.44
rc20531330.5331321.7500.0031353.5402.4131360.3902.92
rc20631190.7531191.1300.0331204.9301.1931207.7701.43
rc207
## 31004.383995.5200.0031015.602.0231010.6601.52
rc208
## 3837.823838.0300.033838.4100.073838.0300.03
## Average00.350.050.460.020.75
t(min)15.3416.2216.01
Table  4:   Comparison  of  the  effect  of  different  heuristic  components:   VNS/TS  denotes  the
standard setting of a hybrid VNS with an SA acceptance criterion.  VNS/TS w/o SA denotes
a  combination  of  TS  and  a  VNS  only  accepting  improving  solutions.   TS  denotes  a  pure  TS
without VNS. Gaps are calculated to the best known solution (BKS).
The results show that the VNS/TS heuristic performs best with an average gap of 0.35% to
the BKS. A comparison to the results obtained with VNS/TS w/o SA allows to quantify the
impact of the SA-based acceptance criterion.  Using SA instead of simply accepting improving
solutions yields a reduction of the gap of 0.1% on average.  Comparing the results to those of the
pure TS, we can see that the hybridization of VNS and TS reduces the gap to the best solution
by more than half.  Overall, the results show the positive effect of the hybridization of VNS, TS
and SA. The solution quality is improved by every component incorporated into our heuristic,
while computing times remain stable on a moderate level.
## 14

5.3  Performance on Benchmark Instances of Related Problems
The E-VRPTW is closely related to the MDVRPI and the G-VRP. For both problems, sets of
benchmark instances exist.  To demonstrate the performance of our VNS/TS heuristic on large
problem sets, we solve all benchmark instances available for the related problems and compare
the  results  obtained  to  those  reported  for  the  competing  algorithms,  which  were  specifically
designed for MDVRPI and G-VRP.
## 5.3.1    MDVRPI
For the MDVRPI (respectively the VRPIF), two benchmark sets with a total of 76 instances
are available from the literature.  The first set of benchmark instances was proposed by Crevier
et al. (2007) and includes 22 instances.  The instances consist of 48-216 customers, 3-6 depots
and 4-6 vehicles.  Depots are centered and customers are located in clusters.  The second set
was designed by Tarantilis et al. (2008) and involves 54 instances.  The set consists of 18 depot-
customer  combinations,  which  were  created  following  the  design  described  in  Crevier  et  al.
(2007) and compromise 50-175 customers and 3-8 depots.  From each of these 18 depot-customer
combinations, three instances were created differing in the number of vehicles available.  In all
instances, travel time is assumed to be equal to travel distance and distances between vertices
are computed as Euclidean distances from the given coordinates.
In Table 5, we compare the results obtained with our VNS/TS on the instance set of Crevier
et al. (2007) to the solutions of the heuristic proposed in Tarantilis et al. (2008),  denoted as
HGL,  and  in  Crevier  et  al.  (2007),  denoted  as  CCL.  For  CCL  and  our  VNS/TS,  we  provide
the best solution found in 10 runs (L
best
(S)) and the computing time in minutes (t(min)).  By
contrast, the value given in columnL
best
(S) for HGL corresponds to the best solution ever found
with the final parameter setting.  We further provide the gap of the best (∆
best
) and average
solution  (∆
avg
)  to  the  best  known  solution  (BKS).  Additionally,  the  last  column  (
## VNS/TS)
shows the best solutions that we found with our VNS/TS heuristic during the overall testing as
well as the percentage improvement to the formerly best known solutions.
Considering the complete set, our VNS/TS heuristic clearly outperforms the CCL approach
in  terms  of  solution  quality  and  speed.   We  obtain  an  average  gap  to  the  best  solution  of
0.18% in about 27 minutes on average, while CCL achieves a 0.66% gap requiring more than
double  our  computing  time.   In  addition,  we  found  10  new  overall  best  solutions  during  the
testing.  Tarantilis et al. (2008) solved only the first subset of instances with their HGL approach.
Compared to their results, we are on average 0.48% worse, however, a direct comparison is not
fair, since the HGL results correspond to the best solution they ever found during their testing.
Table 6 compares the results of our VNS/TS heuristic with those of HGL on the instance
set of Tarantilis et al. (2008).  On those instances, our VNS/TS heuristic shows a really strong
performance.  Our results are on average 0.05% better than those of HGL. This is even more
impressive when considering the fact that they provide only the best solution ever found.  The
gap of the average solution found by our VNS/TS is 1.44% and is hence also lower than the 1.6%
gap of HGL. During our overall testing activities, we additionally obtained new best solutions
for the majority of instances that improve the former ones by 0.45% on average.
## 5.3.2    G-VRP
The benchmark instances for the G-VRP were proposed in Erdogan and Miller-Hooks (2012)
and  consist  of  four  sets,  each  involving  ten  instances  with  20  customers  each.   The  instances
differ in the customer distribution (random or clustered) and the number of available AFS (2
to 10).  Furthermore, Erdogan and Miller-Hooks (2012) present a case study with 12 instances
incorporating up to 500 customers.
Note that some customers contained in the small instances are infeasible, i.e., they cannot
be served under the given restriction that each customer has to be reached in time with at most
## 15

## CCLHGLVNS/TSVNS/TS
Inst.BKSL
best
## (S)  ∆
best
## ∆
avg
t(min)L
best
## (S)∗∆
best
## *  ∆
avg
t(min)L
best
## (S)  ∆
best
## ∆
avg
t(min)L
best
## (S)  ∆
best
## (%)(%)(%)(%)(%)(%)(%)
a11179.791203.39    2.00   2.674.581179.790.000.843.41179.790.00   1.511.821179.790.00
b11217.07
## 1217.07    0.00   1.289.171217.070.000.667.81217.070.00   0.807.141217.070.00
c11883.051888.22    0.27   0.53    36.221883.050.000.8434.21897.30.76   2.2433.931897.30.76
d11059.43
## 1059.43    0.00   1.598.551059.430.000.465.91060.10.06   0.341.821059.430.00
e11309.121309.120.00   0.19    13.521309.120.000.008.71309.120.00   2.667.291309.120.00
f11572.171592.25    1.28   1.87    41.411572.170.000.8738.81584.06    0.76   3.0334.611575.57    0.22
g11181.131190.93    0.83   1.77    55.221181.130.000.775.81181.99    0.07   0.814.211181.130.00
h11547.251566.75    1.26   3.31    32.071547.240.001.9611.11566.19    1.22   2.2718.031562.56    0.99
i11925.99
1945.73    1.02   2.60    51.011925.990.001.5742.51953.39    1.42   4.0745.621933.05    0.37
j1   1117.201144.41    2.44   3.99    58.901117.200.001.045.51115.78-0.13   0.314.241115.78-0.13
k11580.39
1586.92    0.41   2.41    64.611580.390.000.7212.11586.64    0.40   1.3518.111580.92    0.03
l11880.60
1897.74    0.91   1.94   104.271880.600.001.2751.41902.72    1.18   2.7846.141894.05    0.72
## Avg.   0.87   2.01    39.960.000.92    18.920.48   1.8518.58
a2997.941000.24    0.23   0.726.4997.940.00   0.471.8997.940.00
b2   1307.281307.28    0.00   1.9814.71301.21   -0.46   1.347.351291.19-1.23
c2   1747.61
## 1751.45    0.22   2.5761.71732.19   -0.88   0.7618.051719.47-1.61
d2   1871.421877.03    0.30   1.4340.51892.62    1.13   1.9735.11866.97-0.24
e2   1942.851974.13    1.61   2.7273.81940.52   -0.12   2.6159.121928.06-0.76
f2   2284.35
## 2298.51    0.62   1.22    162.22292.40.35   1.7989.862275.28-0.40
g2   1162.58
## 1162.58    0.00   2.0129.51158.21   -0.38  -0.094.141152.92-0.83
h2   1587.37
## 1593.40    0.38   1.54    160.81597.41    0.63   1.4618.351580.55-0.43
i2   1972.001978.70    0.34   1.33    322.41934.09   -1.92  -0.10   47.581925.52-2.36
j2   2294.06
## 2303.01    0.39   1.36    256.92293.4    -0.03   1.5891.32276.52-0.76
## Avg.   0.41   1.69   112.89-0.17   1.1837.27
## Tot.  Avg.   0.66   1.86    73.110.18   1.5427.07
- Note that this value corresponds to the best solution ever obtained with the final parameter setting
Table 5:  Comparison of the solutions obtained on the MDVRPI instances, proposed by Crevier
et al. (2007), to those of HGL and CCL. BKS denotes the previously best known solution.  Gaps
are calculated in dependence of BKS. Additionally, we provide the best solutions inVNS/TS
that we ever obtained on the instances during our testing activities.t(min) denotes the average
runtime for each run.
one  halt  at  an  AFS  for  refueling.   Thus,  these  customers  have  to  be  identified  and  removed
in a preprocessing step.  Erdogan and Miller-Hooks (2012) report solutions found by their two
heuristics  (MCWS  and  DBCA),  as  well  as  solutions  determined  with  the  commercial  solver
ILOG CPLEX. The CPLEX solution is, however, not the optimal solution to the instance.  In
their mathematical formulation, they fixed the number of vehicles required to the value obtained
with the best heuristic in order to get solutions that are comparable, i.e., to determine the best
solution with a given number of vehicles.
We compiled an improved version of their G-VRP model, which is also available online at
http://evrptw.wiwi.uni-frankfurt.de,  and use it to solve the set of small instances with
CPLEX 12.2.  In Table 7, we report the best upper bound found in at most 3 hours of computing
time.  In four cases, CPLEX was not able to determine any feasible solution.  Furthermore, we
solved all instances 10 times by means of our VNS/TS heuristic and report the best solution
found (L
best
(S)) as well as the average computing time in minutes (t(min)).  We compare our
results to those obtained with the MCWS and the DBCA heuristic. Unfortunately, no computing
times are available for those heuristics. In the table, we further report the gap of the best solution
to the solution found by CPLEX (∆).  Columnnprovides the number of feasible customers,
andmthe number of vehicles required.
Our  VNS/TS  heuristic  clearly  outperforms  both  heuristic  methods  proposed  by  Erdogan
and Miller-Hooks (2012), which both achieve an average gap to best solution of about 8%.  On
all instances, we obtain the best solution found by CPLEX or even a solution that improves on
the upper bound, resulting in an average gap of -0.09%.  It is also worth mentioning that we are
able to reduce the number of vehicles in almost half of the instances, while requiring less than
40 seconds of computing time on average.
We additionally solve all large instances of the case study presented by Erdogan and Miller-
Hooks (2012).  In Table 8, we compare the results obtained with our heuristic to those of MCWS
and DBCA. The value given in column ∆ denotes the gap to the best solution found, reported
## 16

## HGLVNS/TSVNS/TS
InstanceBKSL
best
## (S)∗∆
best
## *L
avg
## (S)  ∆
avg
t(min)L
best
## (S)  ∆
best
## L
avg
## (S)  ∆
avg
t(min)L
best
## (S)  ∆
best
## (%)(%)(%)(%)(%)
50c3d2v2209.832209.830.00    2260.02   2.272.852209.830.00   2212.08   0.101.822209.830.00
## 50c3d4v2368.33
## 2368.330.00    2419.86   2.182.232368.330.00    2389.5    0.891.842368.330.00
50c3d6v   3000.883000.880.00    3064.71   2.132.742999.29-0.05   3023.46   0.751.882999.29-0.05
## 50c5d2v2608.25
## 2608.250.0026832.871.542608.250.00   2634.63   1.0122608.250.00
## 50c5d4v3086.58
## 3086.580.00    3124.59   1.232.073086.580.00   3086.58   0.001.983086.580.00
## 50c5d6v3552
## 35520.003583.9    0.903.0435520.00   3562.07   0.282.023548.88-0.09
50c7d2v3353.083353.080.00    3432.68   2.373.163353.83    0.02   3457.14   3.102.383353.080.00
50c7d4v   3381.573381.570.003470.6    2.633.363380.27-0.04   3399.73   0.542.13380.27-0.04
## 50c7d6v    4097.8
## 4097.80.004108.1    0.253.424074.44-0.57   4113.05   0.372.074074.44-0.57
75c3d2v2678.82678.80.00    2694.04   0.574.52692.76    0.52   2723.84   1.684.672678.80.00
75c3d4v2746.742746.740.00    2800.41   1.953.382746.74    0.00   2751.43   0.174.332746.740.00
## 75c3d6v   3454.71
3454.710.00    3499.54   1.304.893448.64   -0.18   3468.77   0.414.343404.34-1.46
75c5d2v3373.693373.690.00    3474.37   2.983.293386.64    0.38   3452.66   2.345.093373.690.00
75c5d4v   3568.353568.350.00    3655.04   2.433.543569.82    0.04   3590.88   0.634.423553.46-0.42
## 75c5d6v   4198.61
## 4198.610.00    4268.19   1.664.184215.30.40   4284.36   2.044.554193.86-0.11
75c7d2v3569.023569.020.00    3655.05   2.415.383581.32    0.34   3627.34   1.635.063569.020.00
75c7d4v   3830.433830.430.00    3911.89   2.135.513830.43    0.00   3895.67   1.704.613825.37-0.13
75c7d6v4239.764239.760.00    4325.33   2.024.294244.35    0.11    4271.7    0.754.84242.08    0.05
100c3d3v3123.513123.510.00    3157.96   1.107.013127.65    0.13   3196.39   2.337.943126.55    0.10
100c3d5v    3552.53552.50.00    3636.56   2.377.313548.75-0.11   3558.91   0.187.623548.44-0.11
## 100c3d7v   4239.83
4239.830.00    4274.86   0.836.624268.34    0.67   4339.03   2.347.924239.5-0.01
## 100c5d3v4053.95
## 4053.950.00    4096.98   1.067.884053.950.00   4118.03   1.588.494053.950.00
100c5d5v4413.174413.170.004531.9    2.697.24424.81    0.26   4656.75   5.527.74415.48    0.05
## 100c5d7v   5148.98
## 5148.980.00    5178.02   0.567.725142.52-0.13   5156.9    0.157.935142.52-0.13
100c7d3v4216.474216.470.00    4242.24   0.618.534242.38    0.61   4284.85   1.628.874216.470.00
100c7d5v   4462.514462.510.00    4523.01   1.368.794448.15   -0.32   4492.44   0.6784439.72-0.51
100c7d7v   4897.474897.470.00    4973.37   1.558.354916.62    0.39   5084.82   3.838.14869.66-0.57
125c4d3v   3920.053920.050.00    3966.16   1.188.733966.61    1.19   4061.97   3.6213.233916.02-0.10
## 125c4d5v   4315.68
## 4315.680.004371.7    1.3094308.44-0.17   4327.81   0.2812.334308.44-0.17
125c4d7v   4763.494763.490.00    4833.91   1.488.44694.32   -1.45   4790.8    0.5712.544668.77-1.99
125c6d3v4064.24064.20.00    4095.72   0.789.194117.41    1.31   4202.41   3.4013.564076.04    0.29
125c6d5v   4826.714826.710.00    4956.95   2.708.334786.74   -0.83   4837.25   0.2213.094765.97-1.26
125c6d7v   5325.285325.280.00    5466.55   2.659.185221.52   -1.95   5295.95  -0.55   12.895164.18-3.03
125c8d3v   4553.284553.280.00    4677.51   2.73    10.234574.82    0.47   4621.98   1.5114.984545.44-0.17
125c8d5v   5045.655045.650.00    5115.35   1.389.644958.26-1.73   5139.14   1.8513.384958.26-1.73
125c8d7v   5416.965416.960.00    5450.87   0.639.345397.86   -0.35   5473.96   1.0513.385347.1-1.29
150c4d3v4049.484049.480.00    4050.08   0.019.714072.95    0.58   4172.94   3.0521.844069.72    0.50
150c4d5v   4638.724638.720.00    4705.63   1.448.194622.77-0.34   4666.79   0.6119.114622.77-0.34
150c4d7v    5176.55176.50.00    5243.96   1.3085163.02   -0.26   5205.56   0.5619.065137.69-0.75
150c6d3v4057.094057.090.00    4063.34   0.159.964066.71    0.24   4116.11   1.4522.074062.53    0.13
150c6d5v4872.084872.080.00    4898.39   0.54    10.234931.13    1.21   4989.97   2.4221.164876.91    0.10
## 150c6d7v   5768.29
5768.290.00    5916.88   2.58    10.735840.52    1.25   5883.53   2.0020.45712.01-0.98
150c8d3v    4653.94653.90.00    4737.16   1.79    10.184689.13    0.76   4823.95   3.6522.674667.50.29
150c8d5v   5113.775113.770.00    5169.84   1.10    11.625116.55    0.05   5200.19   1.6919.65073.8-0.78
150c8d7v   5665.235665.230.00    5665.27   0.00    12.015648.32   -0.30   5693.24   0.4919.675612.02-0.94
175c4d4v4706.764706.760.00    4782.13   1.60    21.744720.36    0.29   4781.93   1.6028.694708.66    0.04
175c4d6v4835.644835.640.00    4960.33   2.58    23.014863.88    0.58   4956.47   2.5026.714841.51    0.12
## 175c4d8v   5943.28
5943.280.00    6034.04   1.5318.45853.9    -1.50   5934.35  -0.15   27.355832.26-1.87
175c6d4v   5025.515025.510.00    5108.08   1.64    21.515011.01   -0.29   5120.82   1.9029.285020.01-0.11
175c6d6v   5431.345431.340.00    5437.14   0.11    22.545382.57   -0.90   5483.57   0.9627.435360.35-1.31
175c6d8v   6090.016090.010.00    6167.31   1.27    25.816066.1    -0.39   6156.06   1.0827.976043.43-0.76
175c8d4v   5878.585878.580.00    6031.02   2.5924.95840.25   -0.65   5954.97   1.3029.835822.55-0.95
175c8d6v   5989.635989.630.00    6157.32   2.80    25.215968.99   -0.34   6123.9    2.2427.785953.54-0.60
175c8d8v   6943.636943.630.00    7075.23   1.9026.76840.04   -1.49   7054.85   1.6027.986775.68-2.42
## Average0.001.609.54-0.051.4412.79-0.45
- Note that this value corresponds to the best solution ever obtained with the final parameter setting
Table 6:  Comparison of the performance of our VNS/TS heuristic on the MDVRPI instances
proposed  by  Tarantilis  et  al.  (2008)  with  the  solutions  of  HGL.  BKS  denotes  the  previously
best known solution.  Gaps are calculated in dependence of BKS. Additionally, we provide the
best solutions in
VNS/TS that we ever obtained on the instances during our testing activities.
t(min) denotes the average runtime for each run.
## 17

## CPLEXMCWSDBCAVNS/TS
m  n  L
best
(S)m   n  L
best
## (S)  ∆(%)L
best
(S)  ∆(%)m  n  L
best
(S)t(min)  ∆(%)
20c3sU16201797.496201818.35    1.161797.510.006201797.490.690.00
20c3sU2
## 6201574.776201614.15    2.50    1613.53    2.466201574.770.640.00
20c3sU36201704.487201969.64   15.56   1964.57   15.266201704.480.640.00
20c3sU4
## 52014826201508.41    1.78    1487.15    0.3552014820.650.00
20c3sU56201689.375201752.73    3.75    1752.73    3.756201689.370.670.00
20c3sU66201618.656201668.16    3.06    1668.16    3.066201618.650.670.00
20c3sU76201713.666201730.45    0.98    1730.45    0.986201713.660.640.00
20c3sU86201706.56201718.67    0.71    1718.67    0.716201706.50.670.00
20c3sU9
## 6201708.816201714.43    0.33    1714.43    0.336201708.810.660.00
20c3sU104201181.315201309.52   10.85   1309.52   10.854201181.310.640.00
20c3sC14201173.575201300.62   10.83   1300.62   10.834201173.570.620.00
20c3sC2
## 5191539.975191553.53    0.88    1553.53    0.885191539.970.580.00
20c3sC3
## 312880.24121083.12   23.05   1083.12   23.05312880.20.250.00
20c3sC44181059.355181135.97.23    1091.78    3.064181059.350.530.00
20c3sC5
## 719-7192190.682190.687192156.010.6
20c3sC68172758.179172883.71    4.55    2883.71    4.558172758.170.710.00
20c3sC7461393.99561701.4    22.05    1701.4    22.05461393.990.180.00
20c3sC89183139.7210183319.74    5.73    3319.74    5.739183139.720.620.00
20c3sC96191799.946191811.05    0.62    1811.05    0.626191799.940.60.00
20c3sC10815-8152648.842644.118152583.420.45
## S12i6s6201578.126201614.15    2.28    1614.15    2.286201578.120.710.00
## S14i6s5201413.965201561.3    10.42   1541.46    9.025201397.270.75-1.18
## S16i6s5201560.496201616.23.571616.23.575201560.490.730.00
## S18i6s6201692.326201902.51   12.42   1882.54   11.246201692.320.740.00
## S110i6s4201173.485201309.52   11.59   1309.52   11.594201173.480.710.00
## S22i6s6201633.16201645.80.781645.80.786201633.10.750.00
## S24i6s5191555.26191505.06-3.221505.06-3.225191532.960.88-1.43
## S2
## 6i6s720-10203115.13115.17202431.330.78
## S28i6s7162158.359162722.55   26.14   2722.55   26.147162158.350.570.00
## S2
## 10i6s617-6161995.621995.626171958.460.61
## S14i2s6201582.216201582.20.001582.20.006201582.210.630.00
## S14i4s5201460.096201580.52    8.25    1580.52    8.255201460.090.680.00
## S14i6s5201397.275201561.29   11.74   1541.46   10.325201397.270.750.00
## S1
## 4i8s6201403.576201561.29   11.24   1561.29   11.246201397.270.82-0.45
## S14i10s5201397.275201536.04    9.93    1529.73    9.485201396.020.85-0.09
## S24i2s4181059.355181135.89    7.23    1117.32    5.474181059.350.510.00
## S24i4s5191446.086191522.72    5.30    1522.72    5.305191446.080.60.00
## S24i6s5201434.146201786.21   24.55   1730.47   20.665201434.140.690.00
## S24i8s5201434.146201786.21   24.55   1786.21   24.555201434.140.750.00
## S24i10s5201434.136201783.63   24.37   1729.51   20.605201434.130.780.00
Average5.58  18.8   1575.986.13  18.78   1781.42    8.52    1774.15    7.945.58  18.8   1645.450.65-0.09
Table 7:  Results on the small-sized G–VRP instances.  Comparison of the solutions obtained
by the MCWS and DBCA heuristics, the solutions determined by our CPLEX implementation
and those of our VNS/TS.L
best
(S) denotes the best solution found in 10 runs, and ∆ the gap
to the best known solution (BKS).t(min) reports the average computing time in minutes.  We
terminate CPLEX after 3 hours, so optimality is for none of the solutions guaranteed.  Numbers
in bold indicate the best solution found.  Note that in some cases, our preprocessing identified a
higher number of feasible customers (numbers in italic) than Erdogan and Miller-Hooks (2012).
## 18

in the first columns.
## BKSMCWSDBCAVNS/TS
m    n   L
best
(S)m    n   L
best
## (S)  ∆(%)L
best
(S)  ∆(%)m    n   L
best
(S)t(min)  ∆(%)
## 111c21171094797.15201095626.64   17.29   5626.64   17.29171094797.1521.760.00
## 111c22171094802.16201095610.57   16.83171094802.1623.560.00
## 111c24171094786.96201095412.48   13.07171094786.9621.90.00
## 111c
## 26171094778.62201095408.38   13.18171094778.6225.120.00
## 111c28171094799.15201095331.93   11.10171094799.1524.170.00
## 200c
## 351928963.463519010428.59  16.35  10413.59  16.18351928963.4676.650.00
## 250c3923710800.184123511886.61  10.06  11886.61  10.063923710800.18120.90.00
300c4628312594.774928114242.56  13.08  14229.92  12.984628312594.77182.23    0.00
350c5132914323.025732916471.10  15.00  16460.30  14.925132914323.02232.03    0.00
400c6137816850.216737819472.10  15.56  19099.04  13.356137816850.21305.12    0.00
## 450c
## 6842418521.237542421854.17  18.00  21854.19  18.006842418521.23525.52    0.00
## 500c7647121170.98447124527.46  15.85  24517.08  15.817647121170.9356.01    0.00
Average38.42  238.25   10598.9842.33  237.75  12189.38  14.61  15510.92  14.8238.42  238.25   10598.98   159.58    0.00
Table  8:  Results  on  the  large-scale  G–VRP  instances.   Comparison  of  the  solutions  obtained
by the MCWS and DBCA heuristics and those of our VNS/TS. Better solutions are marked in
bold; differences below 0.3 are neglected.L
best
(S) denotes the best solution found in 10 runs,
and ∆ the gap to the best known solution (BKS).t(min) reports the average computing time
in minutes.  Numbers in bold indicate the best solution found.  Note that in some cases,  our
preprocessing identified a higher number of feasible customers (numbers in italic) than Erdogan
and Miller-Hooks (2012).
The results obtained by our VNS/TS heuristic on the large instance set is even more impres-
sive.  The solutions of MCWS and DBCA are on average almost 15% worse than our solutions.
In addition, we require significantly less vehicles on average.
To conclude, although our approach is not specifically tailored to the MDVRPI or G-VRP,
we are able to outperform the state-of-the-art heuristics on the G-VRP and the second MDVRPI
benchmark set.  On the first MDVRPI instance, we obtain competitive results while requiring
moderate computing times.
## 6  Conclusion
In this paper, we present a new vehicle routing problem for determining cost-optimal routes for
electric vehicles.  The E-VRPTW considers a limited vehicle and battery capacity and traveling
along arcs consumes battery charge according to a constant consumption factorr.  Vehicles have
the possibility of visiting recharging stations along the route.  The recharging time depends on
the current battery charge on arrival at the station.  Furthermore, customer time windows are
incorporated into the E-VRPTW model in order to represent real-world requirements.
We develop a hybrid VNS/TS heuristic, which makes use of the strong diversification effect
of  VNS  and  involves  a  TS  heuristic  to  efficiently  search  the  solution  space  from  a  randomly
generated solution of the VNS component.  Furthermore, we increase the diversification abilities
of our method by implementing an acceptance criterion based on the Metropolis probability.  In
numerical  studies  performed  on  newly  designed  E-VRPTW  benchmark  instances,  we  demon-
strate the positive effect of combining the two metaheuristics VNS and TS. Moreover, we solve
benchmark  instances  of  the  related  problems  MDVRPI  and  G-VRP.  Although  our  VNS/TS
algorithm is not specifically tailored to solve those problems, it outperforms all competing al-
gorithms on both G-VRP instance sets as well as on the large MDVRPI instance set.  It is also
worth mentioning that we found new best solutions for a large number of benchmark instances
available for MDVRPI and G-VRP.
## References
A. Artmeier, J. Haselmayr, and M. Leucker, M.and Sachenbacher.  The shortest path problem revisited:
Optimal routing for electric vehicles. InKI 2010:  Advances in Artificial Intelligence, LNCS, Volume
## 19

6359, pages 309–316. Springer, 2010.
R. Baldacci, A. Mingozzi, and R. Roberti. Recent exact algorithms for solving the vehicle routing problem
under capacity and time window constraints.European  Journal  of  Operational  Research,  218(1):
## 1–6, 2012.
A. Boostani, R. Ghodsi, and A. K. Miab.  Optimal location of compressed natural gas (CNG) refueling
station using the arc demand coverage model. InProceedings of the 2010 Fourth Asia International
Conference on Mathematical/Analytical Modelling and Computer Simulation, AMS ’10, pages 193–
- IEEE Computer Society, 2010.
O. Br ̈aysy.  A reactive variable neighborhood search for the vehicle routing problem with time windows.
INFORMS Journal on Computing, 15(4):347–368, 2003.
O.  Br ̈aysy  and  M.  Gendreau.   Vehicle  routing  problem  with  time  windows,  Part  II:  Metaheuristics.
## Transportation Science, 39(1):119–139, 2005a.
O. Br ̈aysy and M. Gendreau.  Vehicle routing problem with time windows, Part I: Route construction
and local search algorithms.Transportation Science, 39(1):104–118, 2005b.
J.-F. Cordeau, G. Laporte, and A. Mercier.  A unified tabu search heuristic for vehicle routing problems
with time windows.The Journal of the Operational Research Society, 52(8):928–936, 2001.
B. Crevier, J.-F. Cordeau, and G. Laporte.  The multi-depot vehicle routing problem with inter-depot
routes.European Journal of Operational Research, 176(2):756–773, 2007.
G. B. Dantzig and J. H. Ramser.  The truck dispatching problem.Management Science, 6:80–91, 1959.
S.  Erdogan  and  E.  Miller-Hooks.   A  green  vehicle  routing  problem.Transportation  Research  Part  E:
Logistics and Transportation Review, 48(1):100–114, 2012.
European Comission. White Paper - Roadmap to a single european transport area – Towards a competi-
tive and resource efficient transport system, 2011. URLhttp://eur-lex.europa.eu/LexUriServ/
LexUriServ.do?uri=COM:2011:0144:FIN:EN:PDF.
European Parliament and European Council.  Regulation (EU) No 510/2011 - Setting emission perfor-
mance standards for new light commercial vehicles as part of the union’s integrated approach to
reduceCO
## 2
emissions from light-duty vehicles, 2011.
M. Gendreau and J. Y. Potvin.  Tabu search.  In M. Gendreau and J.Y. Potvin,  editors,Handbook  of
Metaheuristics, pages 41–59. Springer, 2010.
M Gendreau and C. D. Tarantilis.  Solving large-scale vehicle routing problems with time windows:  The
state-of-the-art.  Technical report, CIRRELT-2010-04, 2010.
F. Glover and M. Laguna.Tabu Search.  Kluwer Academic Publishers, 1997.
F. Gon ̧calves, S. R. Cardoso, Relvas S., and A. P. F. D Barbosa-P ́ovoa.  Optimization of a distribution
network using electric vehicles:  A VRP problem.  Technical report, CEG-IST, UTL, Lisboa, 2011.
V. C. Hemmelmayr, K. F. Doerner, and R. F. Hartl. A variable neighborhood search heuristic for periodic
routing problems.European Journal of Operational Research, 195(2):791–802, 2009.
T. Ibaraki, S. Imahori, M. Kubo, T. Masuda, T. Uno, and M. Yagiura.  Effective local search algorithms
for routing and scheduling problems with general time-window constraints.Transportation Science,
## 39(2):206–232, 2005.
B.-I. Kim, S Kim, and S. Sahoo. Waste collection vehicle routing problem with time windows.Computers
## & Operations Research, 33(12):3624–3642, 2006.
G. Kindervater and M. Savelsbergh.  Vehicle routing:  Handling edge exchanges.  In E. Aarts and J.K.
Lenstra,  editors,Local  Search  in  Combinatorial  Optimization,  chapter  10,  pages  337–360.  John
## Wiley & Sons Ltd., 1997.
S. Kirkpatrick, C. D. Gelatt, and M. P. Vecchi. Optimization by simulated annealing.Science, 220(4598):
## 671–680, 1983.
G. Laporte.  Fifty years of vehicle routing.Transportation Science, 43(4):408–416, 2009.
S. Lin.  Computer solutions of the traveling salesman problem.Bell  System  Technical  Journal, 44(10):
## 2245–2269, 1965.
A. Mehrez and H. I. Stern. Optimal refueling strategies for a mixed-vehicle fleet.Naval Research Logistics
## Quarterly, 32(2):315–328, 1985.
J. Melechovsky, C. Prins, and R. Wolfler Calvo. A metaheuristic to solve a location-routing problem with
non-linear costs.Journal of Heuristics, 11(5-6):375–391, 2005.
## 20

A. A. Melkman, H. I. Stern, and A. Mehrez.  Optimal refueling sequence for a mixed fleet with limited
refuelings.Naval Research Logistics Quarterly, 33(4):759–762, 1986.
N. Mladenovi ́c and P. Hansen. Variable neighborhood search.Computers & Operations Research, 24(11):
## 1097–1100, 1997.
Y. Nagata, O. Br ̈aysy, and W. Dullaert. A penalty-based edge assembly memetic algorithm for the vehicle
routing problem with time windows.Computers & Operations Research, 37(4):724–737, 2010.
M. Polacek, R. F. Hartl, K. Doerner, and M. Reimann.  A variable neighborhood search for the multi
depot vehicle routing problem with time windows.Journal of Heuristics, 10(6):613–627, 2004.
J.-Y. Potvin and J.-M. Rousseau. An exchange heuristic for routing problems with time windows.Journal
of the Operational Research Society, 46(12):1433–1446, 1995.
E. Prescott-Gagnon, G. Desaulniers, and L.-M. Rousseau. A branch-and-price-based large neighborhood
search algorithm for the vehicle routing problem with time windows.Networks, 54(4):190–204, 2009.
H. N. Psaraftis.  k-Interchange procedures for local search in a precedence-constrained routing problems.
European Journal of Operational Research, 13(4):391–402, 1983.
Y. Qiu, H. Liu, D. Wang, and X. Liu.  Intelligent strategy on coordinated charging of PHEV with TOU
price.  InPower and Energy Engineering Conference APPEEC 2011 AsiaPacific, pages 1–5, 2011.
Y. Rochat and E. D. Taillard.  Probabilistic diversification and intensification in local search for vehicle
routing.Journal of Heuristics, 1(1):147–167, 1995.
M.  W.  P.  Savelsbergh.   Local  search  in  routing  problems  with  time  windows.Annals  of  Operations
## Research, 4(1):285–305, 1985.
M.  W.  P.  Savelsbergh.   The  vehicle  routing  problem  with  time  windows:  Minimizing  route  duration.
ORSA Journal on Computing, 4(2):146–154, 1992.
M. Schneider, B. Sand, and A. Stenger. A note on the time travel approach for handling time windows in
vehicle routing problems. Working Paper, BISOR, Technical University Kaiserslautern, 2012. URL
http://bisor.wiwi.uni-kl.de/fileadmin/ci/time_travel.pdf.
M. M. Solomon. Algorithms for the vehicle routing and scheduling problems with time window constraints.
## Operations Research, 35(2):254–265, 1987.
A. Stenger, D. Vigo, S. Enz, and M. Schwind. An adaptive variable neighborhood search algorithm for a
vehicle routing problem arising in small package shipping.Transportation Science, page forthcoming,
## 2011.
C. D. Tarantilis, E. E. Zachariadis, and C. T. Kiranoudis.  A hybrid guided local search for the vehicle-
routing problem with intermediate replenishment facilities.INFORMS  Journal  on  Computing, 20
## (1):154–168, 2008.
P. M. Thompson and J. B. Orlin. Theory of cyclic transfers. Working Paper, Operations Research Center,
MIT, Cambridge, Mass, 1989.
P. M. Thompson and H. N. Psaraftis.  Cyclic transfer algorithms for multivehicle routing and scheduling
problems.Operations Research, 41(5):935–946, 1993.
P.  Toth  and  D.  Vigo.   The  granular  tabu  search  and  its  application  to  the  vehicle-routing  problem.
INFORMS Journal on Computing, 15(4):333–346, 2003.
H. Wang and J. Shen. Heuristic approaches for solving transit vehicle scheduling problem with route and
fueling time constraints.Applied Mathematics and Computation, 190(2):1237–1249, 2007.
Y.-W. Wang and C.-C. Lin.  Locating road-vehicle refueling stations.Transportation  Research  Part  E:
Logistics and Transportation Review, 45(5):821–829, 2009.
Y.-W. Wang and C.-R. Wang.  Locating passenger vehicle refueling stations.Transportation  Research
Part E: Logistics and Transportation Review, 46(5):791–801, 2010.
## 21