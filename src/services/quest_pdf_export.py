from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import io
import math
import ssl
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

import certifi
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from src.models.quest_points import QuestPointModel
from src.models.quests import QuestModel

PAGE_WIDTH, PAGE_HEIGHT = A4
PDF_FONT_NAME = "QuestExportFont"
PDF_FONT_PATHS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
OSM_TILE_URL = "https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
OSM_USER_AGENT = "StrelkaBackQuestExport/1.0"
MAP_TILE_SIZE = 256
MAP_WIDTH_PX = 960
MAP_HEIGHT_PX = 460
MAP_ZOOM = 15
TILE_DOWNLOAD_WORKERS = 4
TILE_REQUEST_TIMEOUT_SECONDS = 4
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class QuestPdfExportService:
    @classmethod
    def build_quest_pdf(cls, quest: QuestModel) -> bytes:
        font_name = cls._get_pdf_font_name()
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle(quest.title)
        styles = cls._build_pdf_styles(font_name)

        cls._draw_cover_page(pdf, quest, styles)
        for index, point in enumerate(cls._sorted_points(quest), start=1):
            pdf.showPage()
            cls._draw_checkpoint_page(pdf, point, index, styles)

        pdf.save()
        return buffer.getvalue()

    @classmethod
    def _draw_cover_page(
        cls,
        pdf: canvas.Canvas,
        quest: QuestModel,
        styles: dict[str, ParagraphStyle],
    ) -> None:
        margin = 18 * mm
        cls._draw_page_background(pdf)
        cls._draw_cover_decor(pdf)

        cls._draw_paragraph(
            pdf,
            cls._pdf_text(quest.title),
            styles["CoverTitle"],
            margin,
            PAGE_HEIGHT - 60 * mm,
            PAGE_WIDTH - 2 * margin,
        )

        y = PAGE_HEIGHT - 104 * mm
        card_gap = 4 * mm
        card_width = (PAGE_WIDTH - 2 * margin - 3 * card_gap) / 4
        meta_items = (
            ("Локация", quest.location),
            ("Сложность", f"{quest.difficulty}/5"),
            ("Длительность", f"{quest.duration_minutes} мин."),
            ("Чекпоинтов", str(len(cls._sorted_points(quest)))),
        )
        for item_index, (label, value) in enumerate(meta_items):
            x = margin + item_index * (card_width + card_gap)
            cls._draw_meta_card(pdf, label, value, styles, x, y - 28 * mm, card_width, 31 * mm)

        y -= 48 * mm
        y = cls._draw_labeled_block(
            pdf,
            "Описание",
            quest.description,
            styles,
            margin,
            y,
            PAGE_WIDTH - 2 * margin,
            accent_color="#36B37E",
        )
        if quest.rules_and_warnings:
            y -= 8 * mm
            cls._draw_labeled_block(
                pdf,
                "Правила и предупреждения",
                quest.rules_and_warnings,
                styles,
                margin,
                y,
                PAGE_WIDTH - 2 * margin,
                accent_color="#FFAB00",
            )

        pdf.setFillColor(colors.HexColor("#7A869A"))
        pdf.setFont(styles["Body"].fontName, 8)
        pdf.drawString(margin, 14 * mm, "Экспорт квеста. Ответы расположены внизу страниц чекпоинтов перевёрнутым текстом.")

    @classmethod
    def _draw_checkpoint_page(
        cls,
        pdf: canvas.Canvas,
        point: QuestPointModel,
        index: int,
        styles: dict[str, ParagraphStyle],
    ) -> None:
        margin = 15 * mm
        cls._draw_page_background(pdf)

        cls._draw_checkpoint_badge(pdf, index, margin + 7 * mm, PAGE_HEIGHT - 19 * mm, styles["Body"].fontName)

        cls._draw_paragraph(
            pdf,
            cls._pdf_text(point.title),
            styles["CheckpointTitle"],
            margin + 18 * mm,
            PAGE_HEIGHT - 14 * mm,
            PAGE_WIDTH - 2 * margin - 18 * mm,
        )

        map_x = margin
        map_y = PAGE_HEIGHT - 119 * mm
        map_width = PAGE_WIDTH - 2 * margin
        map_height = 82 * mm
        map_image = cls._build_checkpoint_map(point.latitude, point.longitude)
        cls._draw_card(pdf, map_x - 2 * mm, map_y - 2 * mm, map_width + 4 * mm, map_height + 4 * mm, radius=5 * mm)
        pdf.drawImage(ImageReader(map_image), map_x, map_y, width=map_width, height=map_height, mask="auto")
        pdf.setStrokeColor(colors.HexColor("#B3BAC5"))
        pdf.roundRect(map_x, map_y, map_width, map_height, 3 * mm, fill=0, stroke=1)

        y = map_y - 11 * mm
        coordinates = f"Координаты: {point.latitude:.6f}, {point.longitude:.6f}"
        cls._draw_paragraph(pdf, coordinates, styles["Small"], margin, y, PAGE_WIDTH - 2 * margin)

        y -= 16 * mm
        y = cls._draw_labeled_block(
            pdf,
            "Вопрос",
            point.task,
            styles,
            margin,
            y,
            PAGE_WIDTH - 2 * margin,
            accent_color="#0052CC",
        )
        if point.hint:
            y -= 6 * mm
            y = cls._draw_labeled_block(
                pdf,
                "Подсказка",
                point.hint,
                styles,
                margin,
                y,
                PAGE_WIDTH - 2 * margin,
                accent_color="#6554C0",
            )
        if point.point_rules:
            y -= 6 * mm
            cls._draw_labeled_block(
                pdf,
                "Правила точки",
                point.point_rules,
                styles,
                margin,
                y,
                PAGE_WIDTH - 2 * margin,
                accent_color="#FF991F",
            )

        cls._draw_rotated_answer(pdf, point.correct_answer, styles["Answer"])

    @staticmethod
    def _draw_page_background(pdf: canvas.Canvas) -> None:
        pdf.setFillColor(colors.HexColor("#F7F9FC"))
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#EDF2F7"))
        pdf.circle(PAGE_WIDTH - 22 * mm, PAGE_HEIGHT - 18 * mm, 30 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#E9F5EF"))
        pdf.circle(12 * mm, 22 * mm, 24 * mm, fill=1, stroke=0)

    @staticmethod
    def _draw_cover_decor(pdf: canvas.Canvas) -> None:
        pdf.setFillColor(colors.HexColor("#E6FCFF"))
        pdf.circle(PAGE_WIDTH / 2, PAGE_HEIGHT - 42 * mm, 8 * mm, fill=1, stroke=0)
        pdf.setStrokeColor(colors.HexColor("#36B37E"))
        pdf.setLineWidth(1.2)
        pdf.line(PAGE_WIDTH / 2 - 22 * mm, PAGE_HEIGHT - 82 * mm, PAGE_WIDTH / 2 + 22 * mm, PAGE_HEIGHT - 82 * mm)

    @staticmethod
    def _draw_checkpoint_badge(pdf: canvas.Canvas, index: int, x: float, y: float, font_name: str) -> None:
        radius = 6.2 * mm
        pdf.setFillColor(colors.HexColor("#F25F5C"))
        pdf.circle(x, y, radius, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont(font_name, 10)
        # drawCentredString uses the text baseline, so compensate to keep digits visually centered.
        pdf.drawCentredString(x, y - 1.25 * mm, str(index))

    @classmethod
    def _draw_labeled_block(
        cls,
        pdf: canvas.Canvas,
        title: str,
        text: str,
        styles: dict[str, ParagraphStyle],
        x: float,
        y: float,
        width: float,
        accent_color: str = "#0052CC",
    ) -> float:
        estimated_height = min(max(len(text) / 85 * 8 * mm, 26 * mm), 58 * mm)
        cls._draw_card(pdf, x, y - estimated_height, width, estimated_height + 5 * mm, radius=4 * mm)
        pdf.setFillColor(colors.HexColor(accent_color))
        pdf.roundRect(x, y - estimated_height, 2.2 * mm, estimated_height + 5 * mm, 1 * mm, fill=1, stroke=0)
        content_x = x + 8 * mm
        content_width = width - 14 * mm
        y = cls._draw_paragraph(pdf, f"<b>{cls._pdf_text(title)}</b>", styles["SectionTitle"], content_x, y - 4 * mm, content_width)
        return cls._draw_paragraph(pdf, cls._pdf_text(text), styles["Body"], content_x, y - 1 * mm, content_width)

    @staticmethod
    def _draw_card(pdf: canvas.Canvas, x: float, y: float, width: float, height: float, radius: float = 5 * mm) -> None:
        pdf.setFillColor(colors.HexColor("#D8DEE9"))
        pdf.roundRect(x + 1.4 * mm, y - 1.4 * mm, width, height, radius, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(colors.HexColor("#E6EAF0"))
        pdf.roundRect(x, y, width, height, radius, fill=1, stroke=1)

    @classmethod
    def _draw_meta_card(
        cls,
        pdf: canvas.Canvas,
        label: str,
        value: str,
        styles: dict[str, ParagraphStyle],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        cls._draw_card(pdf, x, y, width, height, radius=4 * mm)
        cls._draw_paragraph(pdf, cls._pdf_text(label).upper(), styles["MetaLabel"], x + 4 * mm, y + height - 6 * mm, width - 8 * mm)
        cls._draw_paragraph(pdf, cls._pdf_text(value), styles["MetaValue"], x + 4 * mm, y + height - 17 * mm, width - 8 * mm)

    @staticmethod
    def _draw_paragraph(
        pdf: canvas.Canvas,
        text: str,
        style: ParagraphStyle,
        x: float,
        y: float,
        width: float,
    ) -> float:
        paragraph = Paragraph(text, style)
        _, height = paragraph.wrap(width, y - 18 * mm)
        paragraph.drawOn(pdf, x, y - height)
        return y - height

    @staticmethod
    def _draw_rotated_answer(pdf: canvas.Canvas, answer: str, style: ParagraphStyle) -> None:
        pdf.saveState()
        pdf.translate(PAGE_WIDTH / 2, 16 * mm)
        pdf.rotate(180)
        answer_text = f"Ответ: {answer}"
        paragraph = Paragraph(escape(answer_text), style)
        width = PAGE_WIDTH - 40 * mm
        _, height = paragraph.wrap(width, 18 * mm)
        paragraph.drawOn(pdf, -width / 2, -height / 2)
        pdf.restoreState()

    @classmethod
    def _build_checkpoint_map(cls, latitude: float, longitude: float) -> Image.Image:
        try:
            return cls._build_osm_map(latitude, longitude, MAP_ZOOM, MAP_WIDTH_PX, MAP_HEIGHT_PX)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            return cls._build_map_placeholder(latitude, longitude, MAP_WIDTH_PX, MAP_HEIGHT_PX)

    @classmethod
    def _build_osm_map(
        cls,
        latitude: float,
        longitude: float,
        zoom: int,
        width_px: int,
        height_px: int,
    ) -> Image.Image:
        center_x, center_y = cls._lat_lon_to_tile_pixel(latitude, longitude, zoom)
        left = int(center_x - width_px / 2)
        top = int(center_y - height_px / 2)
        first_tile_x = left // MAP_TILE_SIZE
        first_tile_y = top // MAP_TILE_SIZE
        last_tile_x = (left + width_px) // MAP_TILE_SIZE
        last_tile_y = (top + height_px) // MAP_TILE_SIZE
        tiles_count = 2**zoom

        canvas_image = Image.new(
            "RGB",
            (
                (last_tile_x - first_tile_x + 1) * MAP_TILE_SIZE,
                (last_tile_y - first_tile_y + 1) * MAP_TILE_SIZE,
            ),
            "#EEF2F6",
        )
        tile_specs: list[tuple[int, int, int, int]] = []
        for tile_x in range(first_tile_x, last_tile_x + 1):
            for tile_y in range(first_tile_y, last_tile_y + 1):
                if tile_y < 0 or tile_y >= tiles_count:
                    continue
                wrapped_tile_x = tile_x % tiles_count
                paste_x = (tile_x - first_tile_x) * MAP_TILE_SIZE
                paste_y = (tile_y - first_tile_y) * MAP_TILE_SIZE
                tile_specs.append((wrapped_tile_x, tile_y, paste_x, paste_y))

        with ThreadPoolExecutor(max_workers=TILE_DOWNLOAD_WORKERS) as executor:
            loaded_tiles = executor.map(
                lambda spec: (
                    cls._download_osm_tile(zoom, spec[0], spec[1]),
                    spec[2],
                    spec[3],
                ),
                tile_specs,
            )
            for tile, paste_x, paste_y in loaded_tiles:
                canvas_image.paste(
                    tile,
                    (paste_x, paste_y),
                )

        crop_left = left - first_tile_x * MAP_TILE_SIZE
        crop_top = top - first_tile_y * MAP_TILE_SIZE
        map_image = canvas_image.crop((crop_left, crop_top, crop_left + width_px, crop_top + height_px))
        cls._draw_map_marker(map_image, width_px // 2, height_px // 2)
        return map_image

    @classmethod
    def _download_osm_tile(cls, zoom: int, tile_x: int, tile_y: int) -> Image.Image:
        tile_data = cls._download_osm_tile_bytes(zoom, tile_x, tile_y)
        return Image.open(io.BytesIO(tile_data)).convert("RGB")

    @staticmethod
    @lru_cache(maxsize=2048)
    def _download_osm_tile_bytes(zoom: int, tile_x: int, tile_y: int) -> bytes:
        url = OSM_TILE_URL.format(zoom=zoom, x=tile_x, y=tile_y)
        request = urllib.request.Request(url, headers={"User-Agent": OSM_USER_AGENT})
        with urllib.request.urlopen(
            request,
            timeout=TILE_REQUEST_TIMEOUT_SECONDS,
            context=SSL_CONTEXT,
        ) as response:
            return response.read()

    @staticmethod
    def _lat_lon_to_tile_pixel(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
        latitude = max(min(latitude, 85.05112878), -85.05112878)
        latitude_rad = math.radians(latitude)
        tiles_count = 2**zoom
        x = (longitude + 180.0) / 360.0 * tiles_count * MAP_TILE_SIZE
        y = (
            (1.0 - math.asinh(math.tan(latitude_rad)) / math.pi)
            / 2.0
            * tiles_count
            * MAP_TILE_SIZE
        )
        return x, y

    @classmethod
    def _build_map_placeholder(
        cls,
        latitude: float,
        longitude: float,
        width_px: int,
        height_px: int,
    ) -> Image.Image:
        image = Image.new("RGB", (width_px, height_px), "#DCE6EF")
        draw = ImageDraw.Draw(image)
        step = 80
        for x in range(0, width_px, step):
            draw.line((x, 0, x, height_px), fill="#C6D1DC", width=2)
        for y in range(0, height_px, step):
            draw.line((0, y, width_px, y), fill="#C6D1DC", width=2)
        cls._draw_map_marker(image, width_px // 2, height_px // 2)

        font = cls._get_image_font(36)
        small_font = cls._get_image_font(24)
        draw.text((44, 42), "Карта недоступна", fill="#243447", font=font)
        draw.text(
            (44, 92),
            f"{latitude:.6f}, {longitude:.6f}",
            fill="#42526E",
            font=small_font,
        )
        return image

    @staticmethod
    def _draw_map_marker(image: Image.Image, x: int, y: int) -> None:
        draw = ImageDraw.Draw(image)
        marker_color = "#E63946"
        border_color = "white"
        draw.ellipse((x - 28, y - 58, x + 28, y - 2), fill=marker_color, outline=border_color, width=5)
        draw.polygon((x - 18, y - 10, x + 18, y - 10, x, y + 34), fill=marker_color)
        draw.ellipse((x - 9, y - 39, x + 9, y - 21), fill=border_color)

    @staticmethod
    def _get_image_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for font_path in PDF_FONT_PATHS:
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size=size)
        return ImageFont.load_default()

    @staticmethod
    def _build_pdf_styles(font_name: str) -> dict[str, ParagraphStyle]:
        base_styles = getSampleStyleSheet()
        body = ParagraphStyle(
            "QuestBody",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#243447"),
            spaceAfter=4,
        )
        return {
            "CoverTitle": ParagraphStyle(
                "QuestCoverTitle",
                parent=body,
                fontSize=34,
                leading=40,
                alignment=1,
                textColor=colors.HexColor("#172B4D"),
                spaceAfter=8,
            ),
            "CheckpointTitle": ParagraphStyle(
                "QuestCheckpointTitle",
                parent=body,
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#172B4D"),
            ),
            "SectionTitle": ParagraphStyle(
                "QuestSectionTitle",
                parent=body,
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#172B4D"),
                spaceBefore=4,
                spaceAfter=4,
            ),
            "Meta": ParagraphStyle(
                "QuestMeta",
                parent=body,
                fontSize=11,
                leading=17,
            ),
            "MetaLabel": ParagraphStyle(
                "QuestMetaLabel",
                parent=body,
                fontSize=6.8,
                leading=8,
                textColor=colors.HexColor("#6B778C"),
            ),
            "MetaValue": ParagraphStyle(
                "QuestMetaValue",
                parent=body,
                fontSize=10.5,
                leading=13,
                textColor=colors.HexColor("#172B4D"),
            ),
            "Small": ParagraphStyle(
                "QuestSmall",
                parent=body,
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#6B778C"),
            ),
            "Answer": ParagraphStyle(
                "QuestAnswer",
                parent=body,
                fontSize=8,
                leading=10,
                alignment=1,
                textColor=colors.HexColor("#42526E"),
            ),
            "Body": body,
        }

    @staticmethod
    def _get_pdf_font_name() -> str:
        if PDF_FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return PDF_FONT_NAME

        for font_path in PDF_FONT_PATHS:
            if font_path.exists():
                pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, str(font_path)))
                return PDF_FONT_NAME

        return "Helvetica"

    @staticmethod
    def _pdf_text(value: str) -> str:
        return "<br/>".join(escape(value).splitlines())

    @staticmethod
    def _sorted_points(quest: QuestModel) -> list[QuestPointModel]:
        return sorted(quest.points or [], key=lambda point: point.id)
