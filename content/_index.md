---
# Leave the homepage title empty to use the site title
title: ''
summary: ''
type: landing

sections:
  - block: resume-biography-3
    content:
      # A folder name within `content/authors/`
      username: me
      text: ''
      # Call-to-action button under the biography. Needs a file in `static/uploads/`.
      # button:
      #   text: Download CV
      #   url: uploads/resume.pdf
      headings:
        about: ''
        education: ''
        interests: ''
    design:
      background:
        gradient_mesh:
          enable: true
      name:
        size: md # xs, sm, md, lg, xl
      avatar:
        size: medium # small, medium, large, xl, xxl
        shape: circle # circle, square, rounded

  - block: collection
    id: papers
    content:
      title: Featured Publications
      filters:
        folders:
          - publications
        featured_only: true
    design:
      view: article-grid
      columns: 2

  - block: collection
    content:
      title: Recent Publications
      text: ''
      filters:
        folders:
          - publications
        exclude_featured: false
    design:
      view: citation

  - block: collection
    id: talks
    content:
      title: Recent & Upcoming Talks
      filters:
        folders:
          - events
    design:
      view: card

  - block: collection
    id: news
    content:
      title: Recent News
      subtitle: ''
      text: ''
      page_type: blog
      # 0 = all pages
      count: 10
      filters:
        author: ''
        category: ''
        tag: ''
        exclude_featured: false
        exclude_future: false
        exclude_past: false
        publication_type: ''
      offset: 0
      # desc or asc
      order: desc
    design:
      view: card
      spacing:
        padding: [0, 0, 0, 0]
---
