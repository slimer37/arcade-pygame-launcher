"""Example program: shows a screen until any key/button is pressed."""
import pygame

pygame.init()
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
font = pygame.font.Font(None, 48)
running = True
while running:
    for event in pygame.event.get():
        if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
            running = False
    screen.fill((30, 30, 60))
    screen.blit(font.render("Hello! Press any key to exit.", True, (255, 255, 255)), (40, 40))
    pygame.display.flip()
pygame.quit()
