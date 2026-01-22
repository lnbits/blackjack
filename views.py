# Description: Add your page endpoints here.

from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

from .crud import get_dealers_by_id

blackjack_generic_router = APIRouter()


def blackjack_renderer():
    return template_renderer(["blackjack/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page


@blackjack_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return blackjack_renderer().TemplateResponse(
        "blackjack/index.html", {"request": req, "user": user.json()}
    )


# Frontend shareable page


@blackjack_generic_router.get("/{dealers_id}")
async def dealers_public_page(req: Request, dealers_id: str):
    dealers = await get_dealers_by_id(dealers_id)
    if not dealers:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Dealers does not exist."
        )

    public_page_name = getattr(dealers, "name", "")
    public_page_description = getattr(dealers, "", "")

    return blackjack_renderer().TemplateResponse(
        "blackjack/game.html",
        {
            "request": req,
            "dealers_id": dealers_id,
            "min_bet": dealers.min_bet,
            "max_bet": dealers.max_bet,
            "public_page_name": public_page_name,
            "public_page_description": public_page_description,
        },
    )
