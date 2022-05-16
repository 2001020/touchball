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
    pygame.Rect(315,420,70,50),[]
    ]
for i in range(200,411,70):
    ctrl[7].append(pygame.Rect(200,i,300,50))
color=[(100,100,100),(100,100,100),(100,100,100),(100,100,100),[]]
#=============
screen = pygame.display.set_mode((700,500))
pygame.display.set_caption("Touch ball experiment")
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            color=[(100,100,100),(100,100,100),(100,100,100),(100,100,100),[]]
            if thread=='start':
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
    screen.fill((70,70,70))
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
    if thread=="start":
        screen.blit(pygame.font.SysFont("arial",40).render("Touch ball experiment",True,(255,255,255)),(150,80))
        for i in range(4):
            pygame.draw.rect(screen,color[i],ctrl[7][i],0)
        for i in range(6):
            if i%2==0:
                screen.blit(myFont.render("+",True,(255,255,255)),ctrl[i])
            if i%2==1:
                screen.blit(myFont.render("-",True,(255,255,255)),ctrl[i])
        for i in range(3):
            screen.blit(myFont.render(["total balls:","touch speed:","ball type:"][i]+str(balldisplay[i]),True,(255,255,255)),(210,210+i*70))
        #
        screen.blit(myFont.render("OK",True,(255,255,255)),ctrl[6])
    if thread == "kind":
        rnum=70*balldisplay[2] if balldisplay[2]<7 else 70*balldisplay[2]+70
        for i in range(0,rnum,70):
            pygame.draw.rect(screen,(100,100,100),[(10+i)//500*350,10+i%500,300,50],0)
            screen.blit(myFont.render("label:error",True,(255,255,255)),((10+i)//500*350+10,20+i%500))
            screen.blit(myFont.render("quantity:error",True,(255,255,255)),((10+i)//500*350+150,20+i%500))
    time.sleep(0.01)
    pygame.display.update()
