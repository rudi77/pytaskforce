# PDF Form Filling Guide

This guide explains how to programmatically fill PDF forms. There are two distinct workflows depending on whether the PDF contains fillable form fields.

## Step 1: Determine Form Type

First, check whether the PDF has fillable form fields:

```bash
python scripts/check_fillable_fields.py input.pdf
```

This will output either:
- `"This PDF has fillable form fields"` - Use the **Fillable Fields Workflow**
- `"This PDF does not have fillable form fields"` - Use the **Non-Fillable Fields Workflow**

---

## Fillable Fields Workflow

Use this workflow when the PDF contains interactive form fields (text boxes, checkboxes, dropdowns, etc.).

### Step 1.1: Extract Field Information

Run the field extraction script:

```bash
python scripts/extract_form_field_info.py input.pdf fields_info.json
```

This generates a JSON file with field details:

```json
[
  {
    "field_id": "name.first",
    "type": "text",
    "page": 1,
    "rect": [72.0, 700.0, 200.0, 720.0]
  },
  {
    "field_id": "agreement",
    "type": "checkbox",
    "page": 1,
    "rect": [72.0, 650.0, 90.0, 668.0],
    "checked_value": "/Yes",
    "unchecked_value": "/Off"
  },
  {
    "field_id": "country",
    "type": "radio_group",
    "page": 1,
    "radio_options": [
      {"value": "/US", "rect": [72.0, 600.0, 90.0, 618.0]},
      {"value": "/UK", "rect": [100.0, 600.0, 118.0, 618.0]}
    ]
  },
  {
    "field_id": "state",
    "type": "choice",
    "page": 1,
    "choice_options": [
      {"value": "CA", "text": "California"},
      {"value": "NY", "text": "New York"}
    ]
  }
]
```

### Step 1.2: Convert to Images (Optional)

For visual verification, convert the PDF to images:

```bash
python scripts/convert_pdf_to_images.py input.pdf ./images/
```

This helps you understand what each field represents.

### Step 1.3: Create Field Values JSON

Create a `field_values.json` file mapping field IDs to values:

```json
[
  {
    "field_id": "name.first",
    "page": 1,
    "value": "John"
  },
  {
    "field_id": "name.last",
    "page": 1,
    "value": "Doe"
  },
  {
    "field_id": "agreement",
    "page": 1,
    "value": "/Yes"
  },
  {
    "field_id": "country",
    "page": 1,
    "value": "/US"
  },
  {
    "field_id": "state",
    "page": 1,
    "value": "CA"
  }
]
```

**Important notes:**
- For **checkboxes**: Use the exact `checked_value` or `unchecked_value` from the field info
- For **radio buttons**: Use one of the values from `radio_options`
- For **choice/dropdown**: Use a value from `choice_options`
- For **text fields**: Use any string value

### Step 1.4: Fill the Form

Run the fill script:

```bash
python scripts/fill_fillable_fields.py input.pdf field_values.json output.pdf
```

The script validates all field IDs and values before writing.

---

## Non-Fillable Fields Workflow

Use this workflow when the PDF is a static document without interactive form fields. This adds text annotations at specific coordinates.

### Step 2.1: Convert PDF to Images

First, convert each page to an image for analysis:

```bash
python scripts/convert_pdf_to_images.py input.pdf ./images/
```

This creates `page_1.png`, `page_2.png`, etc.

### Step 2.2: Analyze and Define Fields

Examine the images to identify where data should be entered. Create a `fields.json` file:

```json
{
  "pages": [
    {
      "page_number": 1,
      "image_width": 850,
      "image_height": 1100
    },
    {
      "page_number": 2,
      "image_width": 850,
      "image_height": 1100
    }
  ],
  "form_fields": [
    {
      "page_number": 1,
      "description": "First Name",
      "label_bounding_box": [50, 200, 150, 220],
      "entry_bounding_box": [160, 200, 350, 220],
      "entry_text": {
        "text": "John",
        "font": "Helvetica",
        "font_size": 12,
        "font_color": "000000"
      }
    },
    {
      "page_number": 1,
      "description": "Last Name",
      "label_bounding_box": [50, 230, 150, 250],
      "entry_bounding_box": [160, 230, 350, 250],
      "entry_text": {
        "text": "Doe",
        "font": "Helvetica",
        "font_size": 12,
        "font_color": "000000"
      }
    },
    {
      "page_number": 1,
      "description": "Checkbox - Agree",
      "label_bounding_box": [50, 280, 200, 300],
      "entry_bounding_box": [210, 282, 226, 298],
      "entry_text": {
        "text": "X",
        "font": "Helvetica",
        "font_size": 14,
        "font_color": "000000"
      }
    }
  ]
}
```

**Bounding box format:** `[x_min, y_min, x_max, y_max]` in image coordinates (pixels).

**Key guidelines:**
- `label_bounding_box`: The area containing the field label (e.g., "First Name:")
- `entry_bounding_box`: The area where data will be placed
- **Boxes must not overlap** - labels and entries must be separate regions
- For checkboxes, use "X" or a checkmark character
- Image dimensions must match the actual converted image size

### Step 2.3: Validate Bounding Boxes

Run the validation script to check for overlapping boxes:

```bash
python scripts/check_bounding_boxes.py fields.json
```

Expected output for valid configuration:
```
Read 3 fields
SUCCESS: All bounding boxes are valid
```

If there are errors, you'll see messages like:
```
FAILURE: intersection between label and entry bounding boxes for `First Name`
```

### Step 2.4: Create Validation Images (Optional)

Visualize the bounding boxes to ensure correct placement:

```bash
python scripts/create_validation_image.py 1 fields.json ./images/page_1.png ./validation_page_1.png
```

This creates an image with:
- **Red rectangles**: Entry bounding boxes (where text goes)
- **Blue rectangles**: Label bounding boxes (field labels)

Inspect the validation image to confirm boxes are positioned correctly.

### Step 2.5: Fill the Form

Once validated, fill the form:

```bash
python scripts/fill_pdf_form_with_annotations.py input.pdf fields.json output.pdf
```

---

## Field Types Reference

### Text Fields

Simple text entry:
```json
{
  "entry_text": {
    "text": "Sample Text",
    "font": "Helvetica",
    "font_size": 12,
    "font_color": "000000"
  }
}
```

### Checkboxes

For fillable forms, use the exact checked/unchecked value:
```json
{
  "field_id": "agree_checkbox",
  "value": "/Yes"
}
```

For non-fillable forms, use X or checkmark:
```json
{
  "entry_text": {
    "text": "X",
    "font": "Helvetica-Bold",
    "font_size": 14
  }
}
```

### Radio Buttons (Fillable Only)

Select one option from the radio group:
```json
{
  "field_id": "gender",
  "value": "/Male"
}
```

### Dropdowns/Choice Fields (Fillable Only)

Select from available options:
```json
{
  "field_id": "country_select",
  "value": "US"
}
```

---

## Coordinate Systems

### Image Coordinates (Non-Fillable Workflow)

- Origin (0, 0) is at the **top-left** corner
- X increases to the right
- Y increases downward
- Units are pixels based on the image resolution

### PDF Coordinates (Fillable Workflow)

- Origin (0, 0) is at the **bottom-left** corner
- X increases to the right
- Y increases upward
- Units are points (1/72 inch)

The `fill_pdf_form_with_annotations.py` script automatically handles coordinate transformation from image to PDF coordinates.

---

## Troubleshooting

### "Field ID not found"

The field ID in your values JSON doesn't match any field in the PDF. Check:
- Spelling and case sensitivity
- Use the exact IDs from `extract_form_field_info.py` output

### "Invalid value for checkbox/radio"

You must use the exact values from the field info. For checkboxes:
- Use `checked_value` (e.g., `/Yes`, `/On`, `/1`)
- Use `unchecked_value` (typically `/Off`)

### Overlapping Bounding Boxes

The validation script detected overlapping regions. Fix by:
- Adjusting coordinates to eliminate overlaps
- Ensuring label and entry boxes don't intersect
- Re-running validation until SUCCESS

### Text Not Visible

If filled text doesn't appear:
- Check font color (use dark color like "000000")
- Verify bounding box size is sufficient for text
- Ensure font size fits within the box height

### Wrong Position

If text appears in wrong location:
- Verify image dimensions match the actual PNG files
- Check coordinate system (image vs PDF coordinates)
- Create validation images to visualize placement

---

## Complete Example

### Filling a Tax Form (Fillable)

```bash
# 1. Extract field info
python scripts/extract_form_field_info.py tax_form.pdf tax_fields.json

# 2. Review the fields
cat tax_fields.json

# 3. Create field values
cat > tax_values.json << 'EOF'
[
  {"field_id": "taxpayer_name", "page": 1, "value": "John Doe"},
  {"field_id": "ssn", "page": 1, "value": "123-45-6789"},
  {"field_id": "filing_status_single", "page": 1, "value": "/Yes"}
]
EOF

# 4. Fill the form
python scripts/fill_fillable_fields.py tax_form.pdf tax_values.json completed_tax_form.pdf
```

### Filling an Application (Non-Fillable)

```bash
# 1. Convert to images
python scripts/convert_pdf_to_images.py application.pdf ./app_images/

# 2. Measure and create fields.json (manual step)
# Use an image editor to find coordinates

# 3. Validate bounding boxes
python scripts/check_bounding_boxes.py app_fields.json

# 4. Create validation image
python scripts/create_validation_image.py 1 app_fields.json ./app_images/page_1.png ./validation.png

# 5. Review validation.png, adjust coordinates if needed

# 6. Fill the form
python scripts/fill_pdf_form_with_annotations.py application.pdf app_fields.json completed_application.pdf
```
