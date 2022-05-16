import pygame,sys,time
pygame.init()
pygame.display.init()
#=============
thread="start"
myFont=pygame.font.SysFont("arial",30)
balldisplay=[0,0,0,{}]#sum,speed,kind
ctrl=[
    pygame.Rect(430,210,20,50),pygame.Rect(450,210,20,50),
    pygame.Rect(430,280,20,50),pygame.Rect(450,280,20,50),
    pygame.Rect(430,350,20,50),pygame.Rect(450,350,20,50),
    pygame.Rect(315,420,70,50),[],[]
    ]
for i in range(200,411,70):
    ctrl[7].append(pygame.Rect(200,i,300,50))
color=[(100,100,100),(100,100,100),(100,100,100),(100,100,100),[]]
number=[[
    pygame.K_0,pygame.K_1,pygame.K_2,pygame.K_3,
    pygame.K_4,pygame.K_5,pygame.K_6,pygame.K_7,
    pygame.K_8,pygame.K_9],
    [0,1,2,3,4,5,6,7,8,9]
    ]
letter=[[
    pygame.K_a,pygame.K_b,pygame.K_c,pygame.K_d,
    pygame.K_e,pygame.K_f,pygame.K_g,pygame.K_h,
    pygame.K_i,pygame.K_j,pygame.K_k,pygame.K_l,
    pygame.K_m,pygame.K_n,pygame.K_o,pygame.K_p,
    pygame.K_q,pygame.K_r,pygame.K_s,pygame.K_t,
    pygame.K_u,pygame.K_v,pygame.K_w,pygame.K_x,
    pygame.K_y,pygame.K_z],
    ["a","b","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a","a",]
    ]
#=============
screen = pygame.display.set_mode((700,500))
pygame.display.set_caption("TouchBall Experiment")
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.KEYDOWN:
            try:
                cindex=color.index((146,182,213)) #cindex=color index
                for i in number[0]:
                    if event.key==i:
                        if balldisplay[cindex]==0:
                            balldisplay[cindex]+=number[1][number[0].index(i)]
                        else:
                            balldisplay[cindex]=int(str(balldisplay[cindex])+str(number[1][number[0].index(i)]))
                    if balldisplay[cindex]>[100,5,13][cindex]:
                        balldisplay[cindex]=int(str(balldisplay[cindex])[0:-1])
                if event.key==pygame.K_BACKSPACE:
                    if len(str(balldisplay[cindex]))==1:
                        balldisplay[cindex]=0
                    balldisplay[cindex]=int(str(balldisplay[cindex])[0:-1])
            except:
                None
        if event.type == pygame.MOUSEBUTTONDOWN:
            color=[(100,100,100),(100,100,100),(100,100,100),(100,100,100),[]]
            if thread=="start":
                for i in range(3):
                    if ctrl[7][i].collidepoint(event.pos):
                        color[i]=(146,182,213)
                if ctrl[0].collidepoint(event.pos):
                    balldisplay[0] += 1
                if ctrl[1].collidepoint(event.pos):
                    balldisplay[0] -= 1
                if ctrl[2].collidepoint(event.pos):
                    balldisplay[1] += 1
                if ctrl[3].collidepoint(event.pos):
                     balldisplay[1] -= 1
                if ctrl[4].collidepoint(event.pos):
                    balldisplay[2] += 1
                if ctrl[5].collidepoint(event.pos):
                    balldisplay[2] -= 1
                if ctrl[6].collidepoint(event.pos):
                    thread="kind"
                    for i in range(len(ctrl[8])):
                        color[4].append((100,100,100))
            if thread=="kind":
                color[4]=[]
                for i in range(len(ctrl[8])):
                    color[4].append((100,100,100))
                for i in ctrl[8]:
                    if i.collidepoint(event.pos):
                        color[4][ctrl[8].index(i)]=(146,182,213)
    if balldisplay[0] > 100:
        balldisplay[0]=100
    if balldisplay[1] > 5:
        balldisplay[1]=5
    if balldisplay[2] > 13:
        balldisplay[2]=13
    if balldisplay[0] < 0 or balldisplay[1] < 0 or balldisplay[2] < 0:
        balldisplay[0]=0
        balldisplay[1]=0
        balldisplay[2]=0
    #====================================
    screen.fill((70,70,70))
    #====================================
    if thread=="start":
        screen.blit(pygame.font.SysFont("arial",30).render("TouchBall Experiment",True,(255,255,255)),(150,80))
        for i in range(4):
            pygame.draw.rect(screen,color[i],ctrl[7][i],0)
        for i in range(6):
            if i%2==0:
                screen.blit(myFont.render("↑",True,(255,255,255)),ctrl[i])
            if i%2==1:
                screen.blit(myFont.render("↓",True,(255,255,255)),ctrl[i])
        for i in range(3):
            screen.blit(myFont.render(["Total Balls:","Touch Speed:","Ball Type:"][i]+str(balldisplay[i]),True,(255,255,255)),(210,210+i*70))
        #
        screen.blit(myFont.render("Continute",True,(255,255,255)),ctrl[6])
    #====================================
    if thread == "kind":
        rnum=70*balldisplay[2] if balldisplay[2]<7 else 70*balldisplay[2]+70
        rect=[]
        for i in range(0,rnum,70):
            rect.append(pygame.Rect((10+i)//500*350,10+i%500,150,50))
            rect.append(pygame.Rect((10+i)//500*350+150,10+i%500,150,50))
        ctrl[8]=rect
        for i in range(len(color[4])):
            pygame.draw.rect(screen,color[4][i],ctrl[8][i],0)
        for i in range(0,rnum,70):
            screen.blit(myFont.render("Label:",True,(255,255,255)),((10+i)//500*350+10,20+i%500))
            screen.blit(myFont.render("Quantity:",True,(255,255,255)),((10+i)//500*350+150,20+i%500))
    time.sleep(0.01)
    pygame.display.update()
